#!/usr/bin/env python3
# Site: Scuderia Car Parts
# Strategy: playwright-rendered (browser transport; server-rendered catalog HTML)
# Discovered base URL: https://www.scuderiacarparts.com/part-finder/
# Last recon: 2026-10-13
# Selectors / fields: see SELECTORS in catalog.py
from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import json
import logging
import os
import uuid
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import grpc
import httpx
from cache_client import ImgCacheClient, WebCacheClient
from playwright.async_api import Error as BrowserError
from playwright.async_api import Request, Route, TimeoutError as BrowserTimeout, async_playwright
from request_auth_client import RequestAuthClient

from catalog import BASE_URL, DOMAIN, CatalogPage, Diagram, Redirected, ScrapeError, catalog_url, parse_catalog

LOGGER = logging.getLogger("scuderia")
CLIENT_NAME = "scuderia_parts"
ROBOTS_URL = BASE_URL + "/robots.txt"
DEFAULT_SEEDS = [
    BASE_URL + "/part-finder/ferrari/458/oe/22/2551/48748",
    BASE_URL + "/part-finder/lamborghini/aventador/oe/181/3155/57087",
    BASE_URL + "/part-finder/mclaren/12c/oe/837/7921/147505",
]
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class Journal:
    """Completion markers commit a diagram's incremental records for resume."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.completed = self._read()
        except (OSError, ScrapeError):
            self.file.close()
            raise

    def _read(self) -> set[str]:
        self.file.seek(0)
        lines = self.file.readlines()
        offset = 0
        batches = {}
        completed = set()
        recovered = False
        for index, line in enumerate(lines):
            try:
                record = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:
                if index == len(lines) - 1 and not line.endswith(b"\n"):
                    LOGGER.warning("Recovering interrupted final JSONL line at byte %s", offset)
                    self.file.truncate(offset)
                    self.file.flush()
                    os.fsync(self.file.fileno())
                    recovered = True
                    break
                raise ScrapeError(f"journal_corrupt: invalid JSONL at byte {offset}") from exc
            if not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("site") != CLIENT_NAME:
                raise ScrapeError(f"journal_corrupt: unknown output schema at byte {offset}")
            batch = record.get("batch_id")
            url = record.get("source_url")
            kind = record.get("record_type")
            if not isinstance(batch, str) or not isinstance(url, str):
                raise ScrapeError(f"journal_corrupt: missing identity at byte {offset}")
            catalog_url(url)
            if kind == "diagram":
                count = record.get("part_rows")
                if batch in batches or not isinstance(count, int) or count < 1:
                    raise ScrapeError("journal_corrupt: invalid diagram header")
                batches[batch] = {"url": url, "expected": count, "rows": set(), "done": False}
            elif kind == "diagram_part":
                state = batches.get(batch)
                source = record.get("source")
                row_id = source.get("row_id") if isinstance(source, dict) else None
                if not state or state["url"] != url or state["done"] or not isinstance(row_id, str) or row_id in state["rows"]:
                    raise ScrapeError("journal_corrupt: invalid membership sequence")
                state["rows"].add(row_id)
            elif kind == "diagram_complete":
                state = batches.get(batch)
                if not state or state["url"] != url or state["done"] or len(state["rows"]) != state["expected"]:
                    raise ScrapeError("journal_corrupt: incomplete completion marker")
                state["done"] = True
                completed.add(url)
            else:
                raise ScrapeError(f"journal_corrupt: unknown record type {kind!r}")
            offset += len(line)
        if lines and not recovered and not lines[-1].endswith(b"\n"):
            self.file.write(b"\n")
            self.file.flush()
            os.fsync(self.file.fileno())
        self.file.seek(0, os.SEEK_END)
        return completed

    def append(self, record: dict) -> None:
        self.file.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        self.file.flush()
        os.fsync(self.file.fileno())

    def save(self, diagram: Diagram, image_hash: str | None, bucket: str) -> None:
        batch = uuid.uuid4().hex
        common = {
            "schema_version": 1, "site": CLIENT_NAME, "batch_id": batch,
            "source_url": diagram.url, "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata = diagram.metadata()
        metadata["image"].update({"imgcache_hash": image_hash, "imgcache_bucket": bucket if image_hash else None})
        self.append({**common, "record_type": "diagram", "part_rows": len(diagram.parts), **metadata})
        for row in diagram.parts:
            source = asdict(row)
            self.append({
                **common, "record_type": "diagram_part", "part_index": row.part_index,
                "part": {
                    "manufacturer": diagram.manufacturer, "url": row.url,
                    "part_number": row.part_number, "title": row.title,
                    "description": row.title,
                },
                "source": source,
            })
        self.append({**common, "record_type": "diagram_complete"})
        self.completed.add(diagram.url)

    def close(self) -> None:
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class BrowserTransport:
    def __init__(self, request_auth: RequestAuthClient, *, cdp_url: str, timeout_ms: int):
        self.auth = request_auth
        self.cdp_url = cdp_url
        self.timeout_ms = timeout_ms
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.owns_context = False
        self.failure: ScrapeError | None = None
        self.statuses: Counter = Counter()
        self.navigation_responses = []
        self.active_permits = set()
        self.robots: RobotFileParser | None = None

    async def _route(self, route: Route, request: Request) -> None:
        host = urlsplit(request.url).hostname
        if host not in (DOMAIN, "challenges.cloudflare.com"):
            await route.abort()
            return
        if host == DOMAIN and self.robots is not None and not self.robots.can_fetch("*", request.url):
            self.failure = ScrapeError(f"robots_disallowed: browser request {urlsplit(request.url).path}")
            await route.abort()
            return
        permit = None
        continued = False
        try:
            permit = await asyncio.to_thread(self.auth.acquire, host)
            self.active_permits.add(permit)
            await route.continue_()
            continued = True
            response = await request.response()
            status = response.status if response else 0
            permit.set_status(status)
            self.statuses[status] += 1
            if status == 429:
                self.failure = ScrapeError("rate_limited: HTTP 429; request-auth informed")
        except (RuntimeError, BrowserError) as exc:
            self.failure = ScrapeError(f"browser_request_failed: {type(exc).__name__}")
            if not continued:
                await route.abort()
        finally:
            if permit is not None:
                permit.release()
                self.active_permits.discard(permit)

    async def _start(self) -> None:
        self.pw = await async_playwright().start()
        try:
            self.browser = await self.pw.chromium.connect_over_cdp(self.cdp_url, timeout=self.timeout_ms)
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
            else:
                self.context = await self.browser.new_context(service_workers="block")
                self.owns_context = True
            self.page = await self.context.new_page()
            await self.page.route("**/*", self._route)
            self.page.on("response", self._response)
        except BrowserError as exc:
            raise ScrapeError("browser_startup: ordinary Chrome/CDP connection failed") from exc

    def _response(self, response) -> None:
        if response.request.is_navigation_request() and response.request.frame == self.page.main_frame:
            self.navigation_responses.append(response)

    def _check_failure(self) -> None:
        if self.failure:
            raise self.failure

    async def fetch(self, url: str, *, binary: bool = False) -> tuple[str | bytes, str]:
        self._check_failure()
        if self.page is None:
            await self._start()
        try:
            # A fresh tab's first request is always a real top-level navigation: it is what passes the
            # Cloudflare challenge and earns clearance for the in-page fetches after it. (Serving a cached
            # robots.txt locally to set the origin skipped that, and every later fetch got 403, 2026-10-14.)
            if urlsplit(self.page.url).hostname != DOMAIN:
                self.navigation_responses.clear()
                await self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                await self.page.wait_for_function(
                    """() => document.body && (document.body.innerText.trim().length > 0 || document.querySelector('img'))
                    && !/just a moment|checking your browser|attention required/i.test(document.title)
                    && !document.querySelector('#challenge-running, #challenge-stage')""",
                    timeout=self.timeout_ms,
                )
                self._check_failure()
                response = self.navigation_responses[-1] if self.navigation_responses else None
                if response is None or response.status != 200 or self.page.url != url:
                    raise ScrapeError(f"access_blocked: startup did not reach requested page {url}")
                content_type = response.headers.get("content-type", "")
                if binary:
                    body = await response.body()
                else:
                    body = (
                        await self.page.locator("body").inner_text()
                        if url == ROBOTS_URL else await self.page.content()
                    )
                return body, content_type
            result = await self.page.evaluate(
                """async ({url, binary, limit, timeout}) => {
                    const r = await fetch(url, {
                        cache: 'no-store', redirect: 'manual',
                        signal: AbortSignal.timeout(timeout)
                    });
                    if (r.type === 'opaqueredirect') return {status: 0, redirected: true};
                    const type = r.headers.get('content-type') || '';
                    if (!binary) return {status: r.status, type, body: await r.text()};
                    const bytes = new Uint8Array(await r.arrayBuffer());
                    if (bytes.length > limit) throw new Error('image exceeds size limit');
                    let encoded = '';
                    for (let i = 0; i < bytes.length; i += 8192)
                        encoded += String.fromCharCode(...bytes.subarray(i, i + 8192));
                    return {status: r.status, type, body: btoa(encoded)};
                }""",
                {"url": url, "binary": binary, "limit": MAX_IMAGE_BYTES, "timeout": self.timeout_ms},
            )
            self._check_failure()
            if result.get("redirected"):
                raise Redirected(f"redirected: {url}")
            if result["status"] != 200:
                raise ScrapeError(f"access_blocked: HTTP {result['status']} at {url}")
            body = base64.b64decode(result["body"], validate=True) if binary else result["body"]
            return body, result["type"]
        except BrowserTimeout as exc:
            self._check_failure()
            navigation_statuses = [response.status for response in self.navigation_responses]
            raise ScrapeError(
                f"browser_timeout: page/challenge did not settle at {url}; "
                f"navigation_statuses={navigation_statuses}; "
                f"target_response_statuses={dict(self.statuses)}; "
                f"active_permits={len(self.active_permits)}"
            ) from exc
        except BrowserError as exc:
            self._check_failure()
            raise ScrapeError(f"browser_transport: request failed at {url}") from exc

    async def close(self) -> None:
        if self.page:
            await self.page.close()
        if self.context and self.owns_context:
            await self.context.close()
        for permit in tuple(self.active_permits):
            permit.release()
        self.active_permits.clear()
        if self.pw:
            await self.pw.stop()


class Collector:
    def __init__(self, web_cache: WebCacheClient, img_cache: ImgCacheClient | None, transport: BrowserTransport, *, bucket: str, max_age: int):
        self.web_cache = web_cache
        self.img_cache = img_cache
        self.transport = transport
        self.bucket = bucket
        self.max_age = max_age
        self.stats = Counter()
        self.robots = None

    async def _html(self, url: str) -> tuple[str, bool]:
        entry = await asyncio.to_thread(self.web_cache.get, url, bucket=self.bucket, max_age=self.max_age)
        if entry is not None:
            self.stats["page_cache_hits"] += 1
            if not isinstance(entry.get("content"), str):
                raise ScrapeError(f"cache_invalid: missing HTML content at {url}")
            return entry["content"], True
        body, content_type = await self.transport.fetch(url)
        if not isinstance(body, str) or (url != ROBOTS_URL and "text/html" not in content_type):
            raise ScrapeError(f"schema_mismatch: unexpected content type at {url}")
        self.stats["live_pages"] += 1
        return body, False

    async def _store(self, url: str, html: str) -> None:
        await asyncio.to_thread(self.web_cache.store, url, html, CLIENT_NAME, bucket=self.bucket)

    async def load_robots(self) -> None:
        raw, cached = await self._html(ROBOTS_URL)
        if not re_has_user_agent(raw):
            raise ScrapeError("robots_unavailable: no valid robots.txt; refusing collection")
        self.robots = RobotFileParser(ROBOTS_URL)
        self.robots.parse(raw.splitlines())
        self.transport.robots = self.robots
        if not cached:
            await self._store(ROBOTS_URL, raw)

    def allowed(self, url: str) -> None:
        if self.robots is None or not self.robots.can_fetch("*", url):
            raise ScrapeError(f"robots_disallowed: {url}")

    async def listing(self, url: str, parse, on_redirect=Redirected):
        """A part-finder listing page (marque / model / OE level) through the same robots, cache and
        permit path as catalogue pages; cached only once `parse` accepts it. A redirect raises, unless
        the caller passes the value it stands for (`on_redirect`)."""
        self.allowed(url)
        try:
            html, cached = await self._html(url)
        except Redirected:
            if on_redirect is Redirected:
                raise
            self.stats["listing_redirects"] += 1
            return on_redirect
        parsed = parse(html, url)
        if not cached:
            await self._store(url, html)
        self.stats["listing_pages"] += 1
        return parsed

    async def page(self, url: str) -> CatalogPage:
        self.allowed(url)
        html, cached = await self._html(url)
        parsed = parse_catalog(html, url)
        if not cached:
            await self._store(url, html)
        return parsed

    async def image(self, url: str) -> str:
        self.allowed(url)
        if self.img_cache is None:
            raise ScrapeError("configuration_error: image cache is required for media collection")
        entry = await asyncio.to_thread(self.img_cache.lookup, url, bucket=self.bucket)
        if entry is not None:
            self.stats["image_cache_hits"] += 1
        else:
            body, content_type = await self.transport.fetch(url, binary=True)
            if not isinstance(body, bytes) or not body or len(body) > MAX_IMAGE_BYTES or not content_type.startswith("image/"):
                raise ScrapeError(f"schema_mismatch: invalid diagram media at {url}")
            entry = await asyncio.to_thread(
                self.img_cache.store, url, body, CLIENT_NAME,
                bucket=self.bucket, filename=Path(urlsplit(url).path).name,
            )
            self.stats["live_images"] += 1
        image_hash = entry.get("hash")
        if not isinstance(image_hash, str) or len(image_hash) != 64:
            raise ScrapeError(f"cache_invalid: missing image content hash at {url}")
        return image_hash

    async def collect(self, seeds: list[str], journal: Journal, *, max_diagrams: int, max_pages: int, metadata_only: bool) -> dict:
        seeds = [catalog_url(seed) for seed in seeds]
        await self.load_robots()
        queue = deque(seeds)
        visited = set()
        diagrams = 0
        parts = 0
        stop = "exhausted"
        while queue:
            url = queue.popleft()
            if url in visited:
                continue
            if url in journal.completed:
                self.stats["resumed_diagrams"] += 1
                visited.add(url)
                continue
            if diagrams >= max_diagrams:
                stop = "diagram_limit"
                break
            if self.stats["catalog_pages"] >= max_pages:
                stop = "page_limit"
                break
            parsed = await self.page(url)
            visited.add(url)
            self.stats["catalog_pages"] += 1
            if parsed.diagram is None:
                queue.extendleft(reversed(parsed.links))
                continue
            diagram = parsed.diagram
            image_hash = None if metadata_only else await self.image(diagram.image_url)
            journal.save(diagram, image_hash, self.bucket)
            diagrams += 1
            parts += len(diagram.parts)
            LOGGER.info("Saved %s membership rows: %s", len(diagram.parts), url)
        return {
            "diagrams": diagrams, "part_rows": parts, "stop": stop,
            "image_mode": "references_only" if metadata_only else "imgcache",
            **self.stats, "target_response_statuses": dict(self.transport.statuses),
        }


def re_has_user_agent(raw: str) -> bool:
    return any(line.strip().lower().startswith("user-agent:") for line in raw.splitlines()) and "<html" not in raw.lower()


def arguments(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Bounded Scuderia catalog collector; no database writes.")
    parser.add_argument("--seed", action="append", help="Variant/category/diagram URL; repeatable. Default: three recon diagrams.")
    parser.add_argument("--output", type=Path, default=Path("output/scuderia.jsonl"))
    parser.add_argument("--max-diagrams", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--max-age", type=int, default=23 * 3600, help="Webcache maximum age in seconds; 0 forces fresh misses.")
    parser.add_argument("--bucket", default=os.environ.get("CACHE_BUCKET", "scuderia"))
    parser.add_argument("--webcache", default=os.environ.get("WEBCACHE_URL"))
    parser.add_argument("--imgcache", default=os.environ.get("IMGCACHE_URL"))
    parser.add_argument("--request-auth", default=os.environ.get("REQUEST_AUTH_SERVER_URL"))
    parser.add_argument("--cdp-url", default=os.environ.get("BROWSERLESS_URL"), help="Required ordinary Chrome/CDP endpoint; use a dedicated browser session.")
    parser.add_argument("--timeout", type=int, default=30, help="Single browser startup/fetch timeout in seconds; no retries.")
    parser.add_argument("--metadata-only", action="store_true", help="Keep image references without downloading source bytes.")
    args = parser.parse_args(argv)
    for name in ("max_diagrams", "max_pages", "timeout"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.max_age < 0:
        parser.error("--max-age must be nonnegative")
    if not args.cdp_url:
        parser.error("set BROWSERLESS_URL or --cdp-url; implicit fresh local browsers are deliberately disabled")
    if not args.webcache or not args.request_auth or (not args.metadata_only and not args.imgcache):
        parser.error("set WEBCACHE_URL, REQUEST_AUTH_SERVER_URL, and IMGCACHE_URL (unless --metadata-only), or use matching flags")
    return args


async def run(args) -> dict:
    with grpc.insecure_channel(args.request_auth) as channel:
        await asyncio.to_thread(grpc.channel_ready_future(channel).result, timeout=10)
    auth = RequestAuthClient(args.request_auth)
    transport = BrowserTransport(auth, cdp_url=args.cdp_url, timeout_ms=args.timeout * 1000)
    try:
        with WebCacheClient(args.webcache) as web_cache:
            if args.metadata_only:
                img_cache = None
                with Journal(args.output) as journal:
                    collector = Collector(web_cache, img_cache, transport, bucket=args.bucket, max_age=args.max_age)
                    return await collector.collect(args.seed or DEFAULT_SEEDS, journal, max_diagrams=args.max_diagrams, max_pages=args.max_pages, metadata_only=True)
            with ImgCacheClient(args.imgcache) as img_cache, Journal(args.output) as journal:
                collector = Collector(web_cache, img_cache, transport, bucket=args.bucket, max_age=args.max_age)
                return await collector.collect(args.seed or DEFAULT_SEEDS, journal, max_diagrams=args.max_diagrams, max_pages=args.max_pages, metadata_only=False)
    finally:
        try:
            await transport.close()
        finally:
            auth.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = arguments(argv)
    try:
        result = asyncio.run(run(args))
    except (ScrapeError, OSError, RuntimeError, ValueError, grpc.FutureTimeoutError, httpx.HTTPError) as exc:
        LOGGER.error("%s: %s", type(exc).__name__, exc)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
