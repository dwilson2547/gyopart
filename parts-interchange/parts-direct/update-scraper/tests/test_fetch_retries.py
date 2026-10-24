"""A page that times out or answers 5xx is retried, then skipped; only a streak of them stops the run."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scraper_v2  # noqa: E402
from scraper_v2 import MAX_FAILED_FETCHES_IN_ROW, PageFetchError, UpdaterV2  # noqa: E402
from utils.Exceptions import PageRetrievalError, SiteUnavailableError  # noqa: E402


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(scraper_v2.time, "sleep", lambda _s: None)


def updater(fail):
    """fail(url, call_number) -> True to make that navigation raise PageFetchError."""
    u = object.__new__(UpdaterV2)  # skip __init__: it needs real service URLs
    u._failed_fetches_in_row = 0
    u.calls = []

    def navigate(url):
        u.calls.append(url)
        if fail(url, sum(c == url for c in u.calls)):
            raise PageFetchError(f"HTTP 520 for {url}")
        return "resp"
    u._navigate = navigate
    return u


def test_transient_failure_is_retried_until_it_loads():
    u = updater(lambda url, n: n <= 2)
    assert u._navigate_retrying("https://example.test/p") == "resp"
    assert len(u.calls) == 3
    assert u._failed_fetches_in_row == 0


def test_page_that_keeps_failing_is_skipped_not_a_stop():
    u = updater(lambda url, n: url.endswith("/dead"))
    with pytest.raises(PageRetrievalError):
        u._navigate_retrying("https://example.test/dead")
    assert len(u.calls) == len(scraper_v2.FETCH_RETRY_WAITS_S) + 1
    u._navigate_retrying("https://example.test/ok")
    assert u._failed_fetches_in_row == 0  # a good page resets the streak


def test_streak_of_failing_pages_stops_the_run():
    u = updater(lambda url, n: True)
    for i in range(MAX_FAILED_FETCHES_IN_ROW - 1):
        with pytest.raises(PageRetrievalError):
            u._navigate_retrying(f"https://example.test/p{i}")
    with pytest.raises(SiteUnavailableError) as ex:
        u._navigate_retrying("https://example.test/last")
    assert not isinstance(ex.value, PageRetrievalError)
    assert "in a row" in str(ex.value)
