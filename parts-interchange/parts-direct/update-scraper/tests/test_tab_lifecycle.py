"""Tab recycling and renderer-crash recovery in UpdaterV2._navigate (no browser, no network)."""
import contextlib
import os
import sys

import pytest
from playwright.sync_api import Error as PlaywrightError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scraper_v2  # noqa: E402
from scraper_v2 import MAX_PAGE_CRASHES, PAGE_RECYCLE_EVERY, RunStopped, UpdaterV2  # noqa: E402


class FakeResp:
    status = 200


class FakePage:
    def __init__(self, crash_on=()):
        self.crash_on = set(crash_on)
        self.url = "https://example.test/"
        self.gotos = 0
        self.closed = False

    def goto(self, url, **_):
        self.gotos += 1
        if url in self.crash_on:
            raise PlaywrightError("Page.goto: Page crashed")
        self.url = url
        return FakeResp()

    def wait_for_timeout(self, _ms):
        pass

    def title(self):
        return "Parts"

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, crash_first_n_pages_on=None):
        self.pages = []
        self.crash = crash_first_n_pages_on  # (url, n): the first n tabs crash on url

    def new_page(self):
        crash_on = ()
        if self.crash and len(self.pages) < self.crash[1]:
            crash_on = (self.crash[0],)
        self.pages.append(FakePage(crash_on))
        return self.pages[-1]


class FakePermit:
    def set_status(self, _status):
        pass


class FakeAuth:
    @contextlib.contextmanager
    def acquire(self, _domain):
        yield FakePermit()


def updater(context):
    u = object.__new__(UpdaterV2)  # skip __init__: it needs real service URLs
    u.request_auth = FakeAuth()
    u._context = context
    u._page = None
    u._page_crashes = 0
    u._new_page()
    return u


def test_tab_is_replaced_after_recycle_limit_and_old_one_closed():
    ctx = FakeContext()
    u = updater(ctx)
    for i in range(PAGE_RECYCLE_EVERY + 1):
        u._navigate(f"https://example.test/p{i}")
    assert len(ctx.pages) == 2
    assert ctx.pages[0].closed and ctx.pages[0].gotos == PAGE_RECYCLE_EVERY
    assert ctx.pages[1].gotos == 1


def test_crash_retries_once_in_a_new_tab():
    ctx = FakeContext(crash_first_n_pages_on=("https://example.test/x", 1))
    u = updater(ctx)
    u._navigate("https://example.test/x")
    assert len(ctx.pages) == 2 and ctx.pages[1].url == "https://example.test/x"
    assert u._page_crashes == 1


def test_crash_on_the_retry_propagates_as_page_crashed():
    ctx = FakeContext(crash_first_n_pages_on=("https://example.test/x", 2))
    u = updater(ctx)
    with pytest.raises(scraper_v2.PageCrashed):
        u._navigate("https://example.test/x")


def test_too_many_crashes_stop_the_run_as_transient():
    ctx = FakeContext(crash_first_n_pages_on=("https://example.test/x", 100))
    u = updater(ctx)
    u._page_crashes = MAX_PAGE_CRASHES
    with pytest.raises(RunStopped) as stop:
        u._navigate("https://example.test/x")
    assert stop.value.exit_code == 75
