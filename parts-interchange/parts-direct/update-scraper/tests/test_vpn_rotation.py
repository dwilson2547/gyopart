"""A VPN exit rotation (proxy unreachable for 30 s - 1 min) is waited out, not a stopped run."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scraper_v2  # noqa: E402
import vpn  # noqa: E402
from scraper_v2 import UpdaterV2  # noqa: E402
from utils.Exceptions import SiteUnavailableError  # noqa: E402


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    clock = [0.0]
    # vpn and scraper_v2 share the time module: one fake clock for both.
    monkeypatch.setattr(vpn.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(vpn.time, "monotonic", lambda: clock[0])


def flaky_check(monkeypatch, down_for):
    calls = []

    def check():
        calls.append(1)
        if len(calls) <= down_for:
            raise vpn.VpnUnavailable("no exit IP")
        return "203.0.113.7"
    monkeypatch.setattr(vpn, "check", check)
    return calls


def test_wait_until_up_rides_out_a_rotation(monkeypatch):
    calls = flaky_check(monkeypatch, down_for=4)  # ~1 min at 15 s polls
    assert vpn.wait_until_up() == "203.0.113.7"
    assert len(calls) == 5


def test_wait_until_up_gives_up_after_the_limit(monkeypatch):
    flaky_check(monkeypatch, down_for=10**6)
    with pytest.raises(vpn.VpnUnavailable):
        vpn.wait_until_up(max_wait_s=60, poll_s=15)


def updater(nav):
    u = object.__new__(UpdaterV2)  # skip __init__: it needs real service URLs
    u._navigate_in_tab = nav
    return u


def test_proxy_drop_mid_run_is_waited_out_and_the_page_retried(monkeypatch):
    flaky_check(monkeypatch, down_for=2)
    tries = []

    def nav(url):
        tries.append(url)
        if len(tries) == 1:
            raise vpn.VpnUnavailable("browser can't reach the VPN proxy: ERR_PROXY_CONNECTION_FAILED")
        return "resp"
    assert updater(nav)._navigate("https://example.test/p") == "resp"
    assert tries == ["https://example.test/p"] * 2


def test_proxy_still_down_stops_as_vpn_unavailable(monkeypatch):
    flaky_check(monkeypatch, down_for=10**6)

    def nav(url):
        raise vpn.VpnUnavailable("ERR_PROXY_CONNECTION_FAILED")
    with pytest.raises(vpn.VpnUnavailable):
        updater(nav)._navigate("https://example.test/p")


class FakeParser:
    def check_page(self, _content):
        return True


def session_updater(fail_first):
    u = object.__new__(UpdaterV2)
    u.parser = FakeParser()
    u._content = lambda: "<html></html>"
    u.opened = 0

    def open_session():
        u.opened += 1
        if u.opened <= fail_first:
            raise scraper_v2.PageFetchError("navigation timed out: https://example.test")
    u._open_session = open_session
    return u


def test_session_start_retries_a_homepage_timeout():
    u = session_updater(fail_first=1)
    u._start_session()
    assert u.opened == 2


def test_session_start_gives_up_after_its_attempts():
    u = session_updater(fail_first=99)
    with pytest.raises(SiteUnavailableError):
        u._start_session()
    assert u.opened == scraper_v2.SESSION_START_ATTEMPTS
