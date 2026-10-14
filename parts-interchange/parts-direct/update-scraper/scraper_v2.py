"""Update scraper v2 (docs/design-v2.md): DB as state, one browser session per run.

A run: VPN check → one stealth browser context → claim a vehicle from scrape_target → crawl it
(categories → diagrams → part pages, through webcache/imgcache, permits from request-auth) → write it in
one transaction → pause → next, until the deadline, the queue is empty, or a stop condition.

Stop conditions raise RunStopped with an exit code for scrape-job-manager:
  75 transient — site unavailable (maintenance / 5xx / challenge that doesn't clear), VPN down
  65 blocked/broken — 403/429, or 5 vehicles in a row failed
"""
from __future__ import annotations

import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

import psycopg2
import requests
from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from cache_client import ImgCacheClient, WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402
from utils.CachedParser import CachedParser  # noqa: E402
from utils.Configs import Configs  # noqa: E402
from utils.Constants import PageType  # noqa: E402
from utils.Exceptions import (  # noqa: E402
    Browser403Error, Browser429Error, InternetDownError, PageRetrievalError, SiteUnavailableError,
)

import vpn  # noqa: E402
import work_queue as q  # noqa: E402
from writer import ScrapedVehicle, Target, write_vehicle  # noqa: E402

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

MAX_CONSECUTIVE_FAILURES = 5
CHALLENGE_WAIT_S = 45
MAX_RECONNECTS = 3  # browser losses per run before stopping (exit 75)
# A tab's renderer grows for as long as it lives: one reused for a whole run reached 6.8 GB in 46 min
# (2026-10-13), slowing every page until navigations timed out, then crashing. A new tab in the same
# context frees that memory and keeps the context's Cloudflare clearance.
PAGE_RECYCLE_EVERY = 100  # live navigations per tab
MAX_PAGE_CRASHES = 5  # renderer crashes per run before stopping (exit 75)
CONTENT_ATTEMPTS = 3  # page.content() reads while a self-started navigation settles
NAV_SETTLE_TIMEOUT_MS = 30_000
IMAGE_WORKERS = 8  # background image downloads per run
PROXY_ERRORS = ("ERR_PROXY_CONNECTION_FAILED", "ERR_TUNNEL_CONNECTION_FAILED", "ERR_PROXY_AUTH",
                "ERR_NO_SUPPORTED_PROXIES", "ERR_MANDATORY_PROXY_CONFIGURATION_FAILED")
INITIAL_VEHICLE_ESTIMATE_S = 30 * 60  # until this run has timed a vehicle itself


def canonical_part_url(url: str) -> str:
    """Part links carry a per-vehicle context query (?c=<base64 of category/vehicle/position>), so one
    part has a different URL on every diagram. The page is the same without it — the 2024 scrape
    fetched and cached part pages bare — so fetch, cache and compare on the bare URL."""
    return url.split("?", 1)[0]


class ImageQueue:
    """Run-wide background image downloads (design-v2 §3.8b).

    Pages submit image URLs as they are parsed and the browser moves straight on; 8 workers download
    alongside the crawl. De-duplicated per run, so an image shared by many cars downloads once. A
    vehicle is written with whatever has finished (saved=true) and the rest as saved=false;
    flush_updates() later flips the ones that completed after their vehicle was written."""

    def __init__(self, download, workers: int):
        from concurrent.futures import ThreadPoolExecutor
        self._download = download
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="img")
        self._futures: dict[str, object] = {}
        self._written_unsaved: set[str] = set()   # written as saved=false, outcome pending
        self.saved = self.failed = 0

    def submit(self, name: str, url: str) -> None:
        if name not in self._futures:
            self._futures[name] = self._pool.submit(self._download, url, name)

    def status(self, name: str) -> bool:
        """saved-so-far for a vehicle write; remembers the ones still pending."""
        f = self._futures.get(name)
        if f is not None and f.done() and not f.cancelled() and f.exception() is None and f.result():
            return True
        if f is not None and not f.done():
            self._written_unsaved.add(name)
        return False

    def pending(self) -> int:
        return sum(1 for f in self._futures.values() if not f.done())

    def flush_updates(self, conn, mfr_id: int) -> int:
        done_ok = [n for n in self._written_unsaved
                   if self._futures[n].done() and not self._futures[n].cancelled()
                   and self._futures[n].exception() is None and self._futures[n].result()]
        finished = [n for n in self._written_unsaved if self._futures[n].done()]
        if done_ok:
            with conn.cursor() as cur:
                cur.execute("UPDATE image SET saved = true WHERE manufacturer_id = %s AND name = ANY(%s)",
                            (mfr_id, done_ok))
            conn.commit()
        self._written_unsaved.difference_update(finished)
        return len(done_ok)

    def drain(self, conn, mfr_id: int, deadline: Optional[datetime]) -> None:
        """Wait for outstanding downloads until the deadline, then record what finished."""
        while self.pending():
            if deadline and datetime.now(timezone.utc).replace(tzinfo=None) >= deadline:
                break
            time.sleep(2)
        self.flush_updates(conn, mfr_id)

    def close(self, cancel: bool) -> None:
        self._pool.shutdown(wait=not cancel, cancel_futures=cancel)
        for f in self._futures.values():
            if f.done() and not f.cancelled() and f.exception() is None:
                if f.result():
                    self.saved += 1
                else:
                    self.failed += 1


def _path(url: str) -> str:
    return urlparse(url or "").path.rstrip("/")


class RunStopped(Exception):
    def __init__(self, exit_code: int, reason: str):
        super().__init__(reason)
        self.exit_code = exit_code
        self.reason = reason


class PageCrashed(Exception):
    """The tab's renderer died (Playwright "Page crashed" / "Target crashed"); the browser is fine."""


class SiteMoved(Exception):
    """The site redirects to another domain (Audi → audi.oempartsonline.com, found 2026-10-11): its
    config and targets need updating, so the run stops as broken (65) instead of misreading pages."""


class VehicleMoved(Exception):
    """The vehicle's URL redirects elsewhere on the site (slugs changed): fail it, never 'no catalogue'."""


class NoCatalog(Exception):
    """The vehicle's page is real but lists no categories."""


class NotOem(NoCatalog):
    """The site sells only aftermarket parts for this vehicle (it redirects to `?brandType=aftermarket`):
    another brand on a multi-make picker (Mopar lists 78 makes, the Toyota dealer 18; found 2026-10-13).
    Recorded like no catalogue, never as a failure."""


@dataclass
class RunStats:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    vehicles_done: int = 0
    no_catalog: int = 0
    failed: int = 0
    cars_created: int = 0
    parts_new: int = 0
    parts_updated: int = 0
    stop_reason: str = ""

    def payload(self) -> dict:
        return {
            "items": self.vehicles_done + self.no_catalog,
            "new": self.cars_created,
            "updated": self.vehicles_done - self.cars_created,
            "no_catalog": self.no_catalog,
            "failed": self.failed,
            "parts_new": self.parts_new,
            "stop": self.stop_reason,
        }


class UpdaterV2:
    def __init__(
        self,
        config_name: str,
        database_url: str,
        deadline: Optional[datetime] = None,
        refresh_after_days: Optional[int] = 180,  # None = no stale refresh
        max_cache_age_days: int = 30,
        spacing_s: tuple[float, float] = (20.0, 60.0),
        max_vehicles: Optional[int] = None,
        discovery: str = "auto",  # auto (when due) | force | skip
        discovery_interval_days: int = 90,
    ):
        cfg = Configs.get(config_name)
        self.config_name = config_name
        self.base_url = cfg["base_url"]
        self.database_url = database_url
        self.deadline = deadline
        self.refresh_after_days = refresh_after_days
        self.max_cache_age_s = max_cache_age_days * 86400
        self.spacing_s = spacing_s
        self.max_vehicles = max_vehicles
        self.discovery = discovery
        self.discovery_interval_days = discovery_interval_days
        self.stats = RunStats()

        self.web_cache = WebCacheClient(os.environ["WEBCACHE_URL"])
        self.img_cache = ImgCacheClient(os.environ["IMGCACHE_URL"])
        self.request_auth = RequestAuthClient(os.environ["REQUEST_AUTH_URL"])
        self.parser = CachedParser(self.base_url)
        self._browser = None
        self._context: "BrowserContext | None" = None
        self._reconnects = 0
        self.last_final_url = ""
        self._page: "Page | None" = None
        self._page_navigations = 0
        self._page_crashes = 0
        self._vehicle_seconds: list[float] = []

    # ── session ────────────────────────────────────────────────────────────────────────────────

    def _connect_browser(self) -> None:
        # Headed Chromium: Cloudflare blocks headless (both the headless shell and new-headless)
        # from the VPN, while a headed browser passes (2026-10-11). In the cluster that browser is
        # scrape-stack's browserless (v1 runs headed sessions on its own display; verified through
        # the VPN 2026-10-11), with the VPN proxy passed per session. Locally, a headed launch.
        proxy = vpn.proxy_url()
        browserless = os.environ.get("BROWSERLESS_URL")
        if browserless:
            browser_proxy = os.environ.get("BROWSER_PROXY_URL") or proxy  # as the browserless pod sees it
            # browserless closes a session after its CONNECTION_TIMEOUT (1h in scrape-stack); one session
            # lasts the whole run here, so ask for one that outlives the deadline.
            left = (self.deadline - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() \
                if self.deadline else 18 * 3600
            # Browserless v2: launch options go as one JSON `launch` parameter (v1's per-flag query
            # parameters are rejected with a 400).
            launch = {"headless": False,
                      "args": ["--window-size=1400,1000", "--disable-blink-features=AutomationControlled"]}
            if browser_proxy:
                launch["args"].append(f"--proxy-server={browser_proxy}")
            import json
            from urllib.parse import urlencode
            query = urlencode({"launch": json.dumps(launch), "timeout": int((max(left, 0) + 30 * 60) * 1000)})
            self._browser = self._pw.chromium.connect_over_cdp(
                browserless + ("&" if "?" in browserless else "?") + query, timeout=60_000)
        else:
            self._browser = self._pw.chromium.launch(
                channel="chromium",
                headless=os.environ.get("BROWSER_HEADLESS") == "1",
                args=["--disable-blink-features=AutomationControlled", "--window-size=1400,1000"],
                proxy={"server": proxy} if proxy else None,
            )
        self._context = None

    def _browser_gone(self, ex: Exception) -> bool:
        return "has been closed" in str(ex) or not self._browser.is_connected()

    def _reconnect(self) -> None:
        """The browser went away mid-run (browserless restart or session timeout): start over with a new
        one rather than failing every remaining vehicle against a dead page."""
        self._reconnects += 1
        if self._reconnects > MAX_RECONNECTS:
            raise RunStopped(75, f"browser lost {self._reconnects} times this run")
        try:
            self._browser.close()
        except Exception:  # noqa: BLE001 — already gone
            pass
        # A restarting browserless takes a while to come back: keep trying for ~2.5 minutes.
        for attempt, wait in enumerate((5, 15, 30, 45, 60), 1):
            time.sleep(wait)
            try:
                self._connect_browser()
                self._open_session()
                break
            except RunStopped:
                raise
            except Exception as ex:  # noqa: BLE001
                print(f"  reconnect attempt {attempt} failed: {type(ex).__name__}: {str(ex)[:120]}", flush=True)
                last = ex
        else:
            raise RunStopped(75, f"could not reconnect the browser: {type(last).__name__}: {last}") from last
        print(f"  browser reconnected ({self._reconnects}/{MAX_RECONNECTS})", flush=True)

    def _open_session(self) -> None:
        if self._context:
            self._context.close()
        # The browser's own, consistent identity. v1 spoofed a Chrome 121 / Windows UA and applied stealth
        # patches; on a current Chromium that mismatch is what got challenged (2026-10-11), while the
        # unmodified headed browser passed.
        self._context = self._browser.new_context(viewport=None, locale="en-US")
        self._page = None
        self._new_page()
        # Homepage first: clears Cloudflare once for the whole session.
        self._navigate(self.base_url)

    def _new_page(self) -> None:
        """Replace the tab, keeping the context (and its cookies). Closing a crashed tab may fail."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:  # noqa: BLE001 — already gone
                pass
        self._page = self._context.new_page()
        self._page_navigations = 0

    def _navigate(self, url: str):
        if self._page_navigations >= PAGE_RECYCLE_EVERY:
            self._new_page()
        try:
            return self._navigate_once(url)
        except PageCrashed as ex:
            self._page_crashes += 1
            if self._page_crashes > MAX_PAGE_CRASHES:
                raise RunStopped(75, f"browser tab crashed {self._page_crashes} times this run") from ex
            print(f"  tab crashed ({self._page_crashes}/{MAX_PAGE_CRASHES}), retrying in a new tab: {url}", flush=True)
            self._new_page()
            return self._navigate_once(url)

    def _navigate_once(self, url: str):
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        domain = urlparse(url).netloc
        with self.request_auth.acquire(domain) as permit:
            self._page_navigations += 1
            try:
                # "load", not "networkidle": the site's background traffic means the network may never go
                # quiet, so networkidle waits out the timeout on perfectly good pages.
                resp = self._page.goto(url, wait_until="load", timeout=60_000)
                self._page.wait_for_timeout(1500)
                # Cloudflare's interstitial can take 15-20 s to clear from the VPN (Ford, 2026-10-11);
                # give it up to CHALLENGE_WAIT_S before check_page calls it unavailable.
                waited = 0
                while waited < CHALLENGE_WAIT_S and self._page.title().startswith("Just a moment"):
                    self._page.wait_for_timeout(3000)
                    waited += 3
                    resp = None  # the response we hold is the challenge's; the page has moved on
            except PlaywrightTimeout as ex:
                # A challenge that never settles looks like this; so does a slow tunnel. Transient.
                permit.set_status(0)
                raise SiteUnavailableError(f"navigation timed out: {url}") from ex
            except PlaywrightError as ex:
                permit.set_status(0)
                if "crashed" in str(ex).lower():
                    raise PageCrashed(str(ex).splitlines()[0]) from ex
                if any(code in str(ex) for code in PROXY_ERRORS):
                    # The proxy itself is unreachable: stop the run, don't fail vehicle after vehicle.
                    raise vpn.VpnUnavailable(f"browser can't reach the VPN proxy: {str(ex)[:120]}") from ex
                raise
            permit.set_status(resp.status if resp else 200)
        final = urlparse(self._page.url).netloc
        if final and final != domain:
            raise SiteMoved(f"{domain} redirects to {final}")
        if resp is not None and resp.status >= 500:
            raise SiteUnavailableError(f"HTTP {resp.status} for {url}")
        return resp

    # ── pages ──────────────────────────────────────────────────────────────────────────────────

    def _content(self) -> str:
        """page.content(), riding out a navigation the page starts on its own after load (a script
        redirect): Playwright refuses with "the page is navigating", which lost a Nissan vehicle
        (2026-10-13). Waits for the new document and reads it instead."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        for attempt in range(1, CONTENT_ATTEMPTS + 1):
            try:
                return self._page.content()
            except PlaywrightError as ex:
                if "is navigating" not in str(ex) or attempt == CONTENT_ATTEMPTS:
                    raise
                try:
                    self._page.wait_for_load_state("load", timeout=NAV_SETTLE_TIMEOUT_MS)
                except PlaywrightTimeout:
                    pass

    def get_page(self, url: str) -> str:
        """Rendered HTML for url, from webcache when fresh and valid; maintenance/challenge pages raise
        SiteUnavailableError and are never cached."""
        # The cache is an optimisation: a webcache error is a miss / a skipped store, never a failed
        # vehicle (a dropped connection lost a 100-category crawl in the first live run, 2026-10-11).
        try:
            cached = self.web_cache.get(url, max_age=self.max_cache_age_s)
        except Exception as ex:  # noqa: BLE001
            print(f"webcache get failed ({type(ex).__name__}), fetching live: {url}")
            cached = None
        if cached:
            if self.parser.check_cached_page(cached["content"]):
                self.last_final_url = url
                return cached["content"]
            try:
                self.web_cache.delete(cached["content_hash"])
            except Exception as ex:  # noqa: BLE001
                print(f"webcache delete failed ({type(ex).__name__})")

        for attempt in (1, 2):
            resp = self._navigate(url)
            self.last_final_url = self._page.url
            if resp is not None and resp.status == 404:
                raise PageRetrievalError(f"404: {url}")
            content = self._content()
            self.last_final_url = self._page.url  # a script redirect may have moved it since goto
            try:
                ok = self.parser.check_page(content)
                break
            except SiteUnavailableError:
                if attempt == 2:
                    raise
                # One fresh session in case it was a challenge tied to the old one.
                self._open_session()
        if not ok:
            raise PageRetrievalError(f"page not found: {url}")
        try:
            self.web_cache.store(url, content, client_name=f"parts-direct-{self.config_name}")
        except Exception as ex:  # noqa: BLE001
            print(f"webcache store failed ({type(ex).__name__}), continuing: {url}")
        return content

    def _with_retries(self, what: str, fn, attempts: int = 3):
        """Retry transient connection trouble: Privoxy's intermittent CONNECT 500s, and imgcache
        connections refused or dropped (in the first parallel run, 2,448 of 10,203 images were lost to a
        local imgcache port-forward restarting under load). Anything else fails straight away."""
        import httpx
        transient = (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
                     httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, ConnectionError)
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except transient as ex:
                if attempt == attempts:
                    raise
                time.sleep(2 * attempt)
                print(f"retrying {what} after {type(ex).__name__} ({attempt}/{attempts - 1})", flush=True)

    def _fetch_image(self, url: str, proxies) -> bytes:
        # Through request-auth like every page fetch, so image traffic is paced, backed off and visible
        # in its admin panel. The CDN domains get a larger pool there (docs/design-v2.md §3.8b); with the
        # default pool of 1 the parallel downloads would serialise again.
        with self.request_auth.acquire(urlparse(url).netloc) as permit:
            resp = requests.get(url, timeout=30, proxies=proxies)
            permit.set_status(resp.status_code)
        resp.raise_for_status()
        return resp.content

    def save_image(self, url: str, name: str) -> bool:
        try:
            if self._with_retries("imgcache lookup", lambda: self.img_cache.lookup(url)):
                return True
            proxy = vpn.proxy_url()
            proxies = {"http": proxy, "https": proxy} if proxy else None
            content = self._with_retries("image download", lambda: self._fetch_image(url, proxies))
            self._with_retries("imgcache store", lambda: self.img_cache.store(
                url=url, file_bytes=content, client_name=f"parts-direct-{self.config_name}", filename=name))
            return True
        except Exception as ex:  # noqa: BLE001 — an image failure never fails the vehicle
            print(f"image failed {url}: {ex}")
            return False

    # ── one vehicle ────────────────────────────────────────────────────────────────────────────

    def _known_parts(self, mfr_id: int, numbers: list[str]) -> dict[str, str]:
        """part_number -> canonical url for parts already stored with a title (no need to re-fetch)."""
        if not numbers:
            return {}
        with psycopg2.connect(self.database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT part_number, coalesce(url, '') FROM part WHERE manufacturer_id = %s "
                "AND part_number = ANY(%s) AND coalesce(title, '') <> ''",
                (mfr_id, numbers),
            )
            return {pn: canonical_part_url(u) for pn, u in cur.fetchall()}

    def crawl(self, t: Target) -> ScrapedVehicle:
        images: dict[str, dict] = {}

        def img(url: str, name: str, alt):
            if name and name not in images:
                full = url if url.startswith("https") else "https:" + url
                images[name] = {"url": full, "alt": alt, "saved": False}
                self.images.submit(name, full)  # downloads in the background while the crawl goes on

        page = self.get_page(t.page_url)
        if _path(self.last_final_url) != _path(t.page_url):
            raise VehicleMoved(f"redirected to {self.last_final_url}")
        if "brandtype=aftermarket" in urlparse(self.last_final_url).query.lower():
            raise NotOem()
        categories = self.parser.parse_cached_page(page, PageType.CATEGORIES)
        if not categories:
            raise NoCatalog()

        diagrams, part_urls = [], {}
        for cat in categories:
            src = self.get_page(cat["url"])  # a failed category page fails the whole vehicle
            diag, plist = self.parser.parse_cached_page(
                src, PageType.DIAGRAMS, {"base_car_url": t.page_url, "category_page_url": cat["url"]})
            for d in diag["diagrams"]:
                img(d.get("img_url") or "", d.get("img") or "", d.get("alt_text"))
            diagrams.append(diag)
            for pn, url in plist.items():
                part_urls.setdefault(pn, canonical_part_url(url))

        known = self._known_parts(t.manufacturer_id, list(part_urls))
        todo = [pn for pn, url in part_urls.items() if known.get(pn) != url]
        print(f"  {len(part_urls)} parts: {len(part_urls) - len(todo)} already stored, {len(todo)} pages to fetch", flush=True)
        parts: dict[str, dict] = {}
        t_parts = time.monotonic()
        for i, pn in enumerate(todo, 1):
            url = part_urls[pn]
            if i % 25 == 0:
                rate = (time.monotonic() - t_parts) / i
                print(f"  part pages {i}/{len(todo)} ({rate:.1f}s each, ~{rate * (len(todo) - i) / 60:.0f} min left)", flush=True)
            try:
                data = self.parser.parse_cached_page(self.get_page(url), PageType.PART)
            except PageRetrievalError:
                parts[pn] = {"url": url, "skipped": True}
                continue
            data["url"] = url
            parts[pn] = data
            for entry in data.get("images", []) or []:
                for key in ("main", "preview", "thumb"):
                    obj = entry.get(key)
                    if obj and obj.get("url"):
                        img(obj["url"], obj["url"].split("/")[-1], None)
        return ScrapedVehicle(diagrams=diagrams, part_numbers=list(part_urls), parts=parts, images=images)

    # ── the run ────────────────────────────────────────────────────────────────────────────────

    def _discovery_due(self, conn) -> bool:
        from discovery import due
        if self.discovery == "skip":
            return False
        if self.discovery == "force":
            return True
        with conn.cursor() as cur:
            is_due = due(cur, self.config_name, self.discovery_interval_days)
        conn.commit()
        return is_due

    def _discover(self, conn, mfr_id: int) -> None:
        """New vehicles first (user, 2026-10-11): when due, list the site's vehicles before working the
        queue, so unknown ones are queued as pending ahead of every stale refresh."""
        from discovery import Discovery
        if self.discovery == "skip":
            return
        if self.discovery == "auto" and not self._discovery_due(conn):
            return
        print(f"discovery: listing {self.config_name} vehicles ({'forced' if self.discovery == 'force' else 'due'})",
              flush=True)
        out_of_time = lambda: bool(self.deadline) and \
            datetime.now(timezone.utc).replace(tzinfo=None) + _seconds(INITIAL_VEHICLE_ESTIMATE_S) > self.deadline
        try:
            Discovery(self, conn, mfr_id, out_of_time).run()
        except (SiteUnavailableError, InternetDownError, vpn.VpnUnavailable) as ex:
            conn.rollback()
            raise RunStopped(75, f"site unavailable during discovery: {ex}") from ex
        except Exception as ex:  # noqa: BLE001 — the queue can still be worked; next run tries again
            conn.rollback()
            print(f"discovery failed, working the queue anyway: {type(ex).__name__}: {str(ex)[:300]}", flush=True)
        self._navigate(self.base_url)  # back to a normal page for the crawl

    def _time_left_for_another(self) -> bool:
        if self.max_vehicles is not None and self.stats.vehicles_done + self.stats.no_catalog + self.stats.failed >= self.max_vehicles:
            self.stats.stop_reason = "max_vehicles"
            return False
        if not self.deadline:
            return True
        est = (sum(self._vehicle_seconds) / len(self._vehicle_seconds)) if self._vehicle_seconds else INITIAL_VEHICLE_ESTIMATE_S
        if datetime.now(timezone.utc).replace(tzinfo=None) + _seconds(est) > self.deadline:
            self.stats.stop_reason = "deadline"
            return False
        return True

    def run(self) -> RunStats:
        try:
            print(f"VPN ok, exit ip {vpn.check()}")
        except vpn.VpnUnavailable as ex:
            raise RunStopped(75, str(ex)) from ex

        conn = psycopg2.connect(self.database_url)
        conn.autocommit = False
        with conn.cursor() as cur:
            mfr_id = q.manufacturer_id(cur, self.config_name)
            counts = q.queue_counts(cur, mfr_id, self.refresh_after_days)
            print("queue:", counts, "| refresh", "off" if self.refresh_after_days is None
                  else f"after {self.refresh_after_days} days")
        conn.commit()
        # Nothing to scrape and discovery not due: stop before touching the site at all, so a daily
        # schedule costs nothing on the days there is no work.
        if not q.anything_due(counts) and not self._discovery_due(conn):
            print("nothing due: no pending vehicles, discovery not due", flush=True)
            self.stats.stop_reason = "nothing_due"
            conn.close()
            self.request_auth.close()
            return self.stats

        from playwright.sync_api import sync_playwright
        consecutive_failures = 0
        self.images = ImageQueue(self.save_image, IMAGE_WORKERS)
        stopped = False
        with sync_playwright() as p:
            proxy = vpn.proxy_url()
            self._pw = p
            self._connect_browser()
            try:
                try:
                    self._open_session()
                    self.parser.check_page(self._content())  # homepage: challenge/block/maintenance?
                except (SiteUnavailableError, vpn.VpnUnavailable) as ex:
                    raise RunStopped(75, f"site unavailable at session start: {ex}") from ex
                except (Browser403Error, Browser429Error) as ex:
                    raise RunStopped(65, f"blocked at session start: {ex}") from ex
                except SiteMoved as ex:
                    raise RunStopped(65, f"site moved: {ex}") from ex
                self._discover(conn, mfr_id)
                while self._time_left_for_another():
                    if (self.stats.vehicles_done + self.stats.no_catalog) % vpn.CHECK_EVERY == 0 and self.stats.vehicles_done:
                        try:
                            vpn.check()
                        except vpn.VpnUnavailable as ex:
                            raise RunStopped(75, str(ex)) from ex
                    with conn.cursor() as cur:
                        t = q.claim_next(cur, mfr_id, self.refresh_after_days)
                    conn.commit()
                    if t is None:
                        self.stats.stop_reason = "queue_empty"
                        break
                    print(f"vehicle {t.id}: {t.year} {t.make} {t.model} {t.trim} {t.engine}")
                    t0 = time.monotonic()
                    try:
                        scraped = self.crawl(t)
                        for name, meta in scraped.images.items():
                            meta["saved"] = self.images.status(name)
                        ws = write_vehicle(conn, self.config_name, t, scraped)
                        conn.commit()
                        late = self.images.flush_updates(conn, mfr_id)
                        self.stats.vehicles_done += 1
                        self.stats.cars_created += ws.car_created
                        self.stats.parts_new += ws.parts_new
                        self.stats.parts_updated += ws.parts_updated
                        consecutive_failures = 0
                        print(f"  done: car {ws.car_id} {'(new)' if ws.car_created else ''} parts={ws.car_parts} "
                              f"diagrams={ws.diagrams} new_parts={ws.parts_new} | images queued={self.images.pending()} "
                              f"late-saved={late}", flush=True)
                    except RunStopped:
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.release(cur, t.id)  # stopped mid-vehicle (e.g. repeated tab crashes): it goes again
                        conn.commit()
                        raise
                    except NoCatalog as ex:
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.mark_no_catalog(cur, t.id)
                        conn.commit()
                        self.stats.no_catalog += 1
                        consecutive_failures = 0
                        print("  not sold by this site (aftermarket only)" if isinstance(ex, NotOem) else "  no catalogue")
                    except (SiteUnavailableError, InternetDownError, vpn.VpnUnavailable) as ex:
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.release(cur, t.id)
                        conn.commit()
                        raise RunStopped(75, f"site unavailable: {ex}") from ex
                    except (Browser403Error, Browser429Error) as ex:
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.release(cur, t.id)
                        conn.commit()
                        raise RunStopped(65, f"blocked: {type(ex).__name__}") from ex
                    except SiteMoved as ex:
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.release(cur, t.id)
                        conn.commit()
                        raise RunStopped(65, f"site moved: {ex}") from ex
                    except Exception as ex:  # noqa: BLE001 — one vehicle's failure is recorded, run goes on
                        if self._browser_gone(ex):
                            conn.rollback()
                            with conn.cursor() as cur:
                                q.release(cur, t.id)  # not the vehicle's fault: it goes again
                            conn.commit()
                            print(f"  browser lost: {type(ex).__name__}", flush=True)
                            self._reconnect()
                            continue
                        conn.rollback()
                        with conn.cursor() as cur:
                            q.mark_failed(cur, t.id, f"{type(ex).__name__}: {ex}")
                        conn.commit()
                        self.stats.failed += 1
                        consecutive_failures += 1
                        print(f"  failed: {type(ex).__name__}: {ex}")
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            raise RunStopped(65, f"{consecutive_failures} vehicles failed in a row; last: {ex}")
                    self._vehicle_seconds.append(time.monotonic() - t0)
                    pause = random.uniform(*self.spacing_s)
                    time.sleep(pause)
                # Let queued images finish (within the deadline) and record them.
                print(f"draining {self.images.pending()} queued images", flush=True)
                self.images.drain(conn, mfr_id, self.deadline)
            except RunStopped as stop:
                self.stats.stop_reason = stop.reason  # before the finally records the run
                stopped = True
                raise
            finally:
                # On a stop (VPN/site down) pending downloads would fail anyway: cancel them; their
                # rows stay saved=false for the image sweep.
                self.images.close(cancel=stopped or sys.exc_info()[0] is not None)
                try:
                    self.images.flush_updates(conn, mfr_id)
                except Exception as ex:  # noqa: BLE001
                    print(f"could not record late image saves: {ex}")
                    conn.rollback()
                print(f"images this run: {self.images.saved} saved, {self.images.failed} failed", flush=True)
                try:
                    self._record_run(conn)
                finally:
                    try:  # the browser may already be gone; that must not skip closing the rest
                        if self._context:
                            self._context.close()
                        self._browser.close()
                    except Exception:  # noqa: BLE001
                        pass
                    conn.close()
                    self.request_auth.close()
        return self.stats

    def _record_run(self, conn) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scrape_run (manufacturer, started_at, completed_at, cars_processed, new_parts, "
                    "updated_parts, success, error_message) VALUES (%s, %s, now() AT TIME ZONE 'utc', %s, %s, %s, %s, %s)",
                    (self.config_name, self.stats.started_at, self.stats.vehicles_done + self.stats.no_catalog,
                     self.stats.parts_new, self.stats.parts_updated, self.stats.stop_reason in ("deadline", "queue_empty", "max_vehicles"),
                     self.stats.stop_reason[:1000] or None),
                )
            conn.commit()
        except Exception as ex:  # noqa: BLE001
            print(f"could not record scrape_run: {ex}")
            conn.rollback()


def _seconds(s: float):
    from datetime import timedelta
    return timedelta(seconds=s)
