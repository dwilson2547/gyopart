import asyncio
import json
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from catalog import ScrapeError, parse_catalog
from scraper import BrowserTransport, Collector, Journal, ROBOTS_URL, arguments

ROBOTS = "User-agent: *\nDisallow: /account/\nDisallow: /images/misc/\nCrawl-delay: 1\n"


def diagram(captured):
    return parse_catalog(captured["html"], captured["source_url"]).diagram


def test_journal_resume_and_lossless_output(captured, tmp_path):
    path = tmp_path / "output.jsonl"
    parsed = diagram(captured)
    with Journal(path) as journal:
        journal.save(parsed, "a" * 64, "scuderia")
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 71
    assert records[0]["image"]["imgcache_hash"] == "a" * 64
    assert len(records[0]["source"]["hotspots"]) == len(parsed.hotspots)
    assert records[1]["part"]["manufacturer"] == "Ferrari"
    assert records[1]["source"]["notes"] == "Not for EU GS, UK"
    assert records[-1]["record_type"] == "diagram_complete"
    with Journal(path) as journal:
        assert journal.completed == {parsed.url}


def test_partial_batch_is_not_completed(captured, tmp_path):
    path = tmp_path / "output.jsonl"
    with Journal(path) as journal:
        journal.save(diagram(captured), None, "scuderia")
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:3]) + b'{"record_type":')
    with Journal(path) as journal:
        assert not journal.completed
        journal.save(diagram(captured), None, "scuderia")
    with Journal(path) as journal:
        assert journal.completed == {captured["source_url"]}


def test_corrupt_complete_line_is_not_silently_skipped(tmp_path):
    path = tmp_path / "output.jsonl"
    path.write_bytes(b"not-json\n")
    with pytest.raises(ScrapeError, match="journal_corrupt"):
        Journal(path)


def test_journal_excludes_other_writers(tmp_path):
    path = tmp_path / "output.jsonl"
    with Journal(path):
        with pytest.raises(BlockingIOError):
            Journal(path)


def test_complete_last_line_without_newline_is_repaired(captured, tmp_path):
    path = tmp_path / "output.jsonl"
    with Journal(path) as journal:
        journal.save(diagram(captured), None, "scuderia")
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with Journal(path) as journal:
        assert captured["source_url"] in journal.completed
    assert path.read_bytes().endswith(b"\n")


def collector(captured, *, cached=True):
    web = Mock()
    entries = {ROBOTS_URL: ROBOTS, captured["source_url"]: captured["html"]}
    web.get.side_effect = lambda url, **kwargs: {"content": entries[url]} if cached else None
    image = Mock()
    image.lookup.return_value = {"content_hash": "a" * 64}
    transport = SimpleNamespace(statuses=Counter(), robots=None, fetch=Mock())
    result = Collector(web, image, transport, bucket="scuderia", max_age=3600)
    return result, web, image, transport


def test_all_cached_run_never_touches_target_and_resumes(captured, tmp_path):
    c, web, image, transport = collector(captured)
    with Journal(tmp_path / "output.jsonl") as journal:
        result = asyncio.run(c.collect([captured["source_url"]], journal, max_diagrams=1, max_pages=5, metadata_only=False))
    assert result["diagrams"] == 1 and result["part_rows"] == 69
    assert result["page_cache_hits"] == 2
    transport.fetch.assert_not_called()
    image.store.assert_not_called()
    web.store.assert_not_called()
    with Journal(tmp_path / "output.jsonl") as journal:
        c, web, image, transport = collector(captured)
        result = asyncio.run(c.collect([captured["source_url"]], journal, max_diagrams=1, max_pages=5, metadata_only=False))
    assert result["diagrams"] == 0 and result["resumed_diagrams"] == 1
    assert web.get.call_count == 1
    transport.fetch.assert_not_called()


def test_bad_cached_html_fails_without_marking_complete(captured, tmp_path):
    c, web, _, _ = collector(captured)
    web.get.side_effect = lambda url, **kwargs: {"content": ROBOTS if url == ROBOTS_URL else "<title>Just a moment...</title>"}
    with Journal(tmp_path / "output.jsonl") as journal:
        with pytest.raises(ScrapeError, match="access_blocked"):
            asyncio.run(c.collect([captured["source_url"]], journal, max_diagrams=1, max_pages=5, metadata_only=True))
        assert not journal.completed
    web.store.assert_not_called()


def test_robots_block_target_even_with_cached_data(captured, tmp_path):
    c, web, _, transport = collector(captured)
    web.get.side_effect = None
    web.get.return_value = {"content": "User-agent: *\nDisallow: /part-finder/\n"}
    with Journal(tmp_path / "output.jsonl") as journal:
        with pytest.raises(ScrapeError, match="robots_disallowed"):
            asyncio.run(c.collect([captured["source_url"]], journal, max_diagrams=1, max_pages=5, metadata_only=True))
    transport.fetch.assert_not_called()


def test_cli_requires_explicit_browser_and_valid_limits(monkeypatch):
    monkeypatch.delenv("BROWSERLESS_URL", raising=False)
    with pytest.raises(SystemExit):
        arguments(["--webcache", "http://cache", "--request-auth", "auth:9000", "--metadata-only"])
    with pytest.raises(SystemExit):
        arguments(["--cdp-url", "http://localhost:9222", "--max-diagrams", "0"])


class Permit:
    def __init__(self):
        self.status = 0
        self.released = False

    def set_status(self, status):
        self.status = status

    def release(self):
        self.released = True


def test_every_allowed_browser_request_reports_real_status():
    auth = Mock()
    permits = [Permit(), Permit(), Permit()]
    auth.acquire.side_effect = permits
    transport = BrowserTransport(auth, cdp_url="http://localhost:9222", timeout_ms=1000)

    async def exercise():
        for status in (200, 403, 429):
            response = SimpleNamespace(status=status)

            async def get_response():
                return response

            async def no_op():
                pass

            request = SimpleNamespace(url=ROBOTS_URL, resource_type="document", response=get_response)
            route = SimpleNamespace(continue_=no_op, abort=no_op)
            await transport._route(route, request)

    asyncio.run(exercise())
    assert auth.acquire.call_count == 3
    assert [p.status for p in permits] == [200, 403, 429]
    assert all(p.released for p in permits)
    assert transport.statuses == {200: 1, 403: 1, 429: 1}
    with pytest.raises(ScrapeError, match="rate_limited"):
        transport._check_failure()


def test_unrelated_browser_traffic_is_blocked_without_permit():
    auth = Mock()
    transport = BrowserTransport(auth, cdp_url="http://localhost:9222", timeout_ms=1000)
    aborted = []

    async def abort():
        aborted.append(True)

    route = SimpleNamespace(abort=abort)
    request = SimpleNamespace(url="https://analytics.example/track")
    asyncio.run(transport._route(route, request))
    assert aborted == [True]
    auth.acquire.assert_not_called()


def test_cached_robots_establishes_origin_without_target_navigation(captured):
    auth = Mock()
    transport = BrowserTransport(auth, cdp_url="http://localhost:9222", timeout_ms=1000)
    transport.cached_robots = ROBOTS
    routes = []
    navigations = []
    fulfilled = []

    async def route(url, handler, **kwargs):
        routes.append((url, handler, kwargs))

    async def goto(url, **kwargs):
        navigations.append(url)
        page.url = url
        local = SimpleNamespace(fulfill=AsyncMock(side_effect=lambda **kwargs: fulfilled.append(kwargs)))
        await routes[-1][1](local)

    async def evaluate(code, data):
        return {"status": 200, "type": "text/html", "body": captured["html"]}

    page = SimpleNamespace(url="about:blank", route=route, goto=goto, evaluate=evaluate)
    transport.page = page

    async def exercise():
        for _ in range(2):
            body, content_type = await transport.fetch(captured["source_url"])
            assert body == captured["html"] and content_type == "text/html"

    asyncio.run(exercise())
    assert navigations == [ROBOTS_URL]
    assert len(fulfilled) == 1
    assert fulfilled[0]["body"] == ROBOTS
    assert routes[0][2] == {"times": 1}
    auth.acquire.assert_not_called()


def test_close_preserves_supplied_browser_context_and_other_tabs():
    transport = BrowserTransport(Mock(), cdp_url="http://localhost:9222", timeout_ms=1000)
    transport.page = SimpleNamespace(close=AsyncMock())
    transport.context = SimpleNamespace(close=AsyncMock())
    transport.browser = SimpleNamespace(close=AsyncMock())
    transport.pw = SimpleNamespace(stop=AsyncMock())
    asyncio.run(transport.close())
    transport.page.close.assert_awaited_once()
    transport.context.close.assert_not_awaited()
    transport.browser.close.assert_not_awaited()
    transport.pw.stop.assert_awaited_once()


def test_category_traversal_respects_page_and_diagram_bounds(captured, tmp_path):
    category_url = captured["source_url"].rsplit("/", 1)[0]
    for max_pages, expected_diagrams, stop in [(1, 0, "page_limit"), (2, 1, "diagram_limit")]:
        c, web, _, transport = collector(captured)
        web.get.side_effect = lambda url, **kwargs: {
            "content": ROBOTS if url == ROBOTS_URL else captured["html"]
        }
        with Journal(tmp_path / f"output-{max_pages}.jsonl") as journal:
            result = asyncio.run(c.collect(
                [category_url], journal, max_diagrams=1, max_pages=max_pages,
                metadata_only=True,
            ))
        assert result["diagrams"] == expected_diagrams
        assert result["stop"] == stop
        assert result["catalog_pages"] == max_pages
        transport.fetch.assert_not_called()
