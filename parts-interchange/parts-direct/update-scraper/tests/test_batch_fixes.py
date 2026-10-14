"""Page reads during a script redirect, aftermarket-only vehicles, and discovery's make filter and
per-vehicle skip (no browser, no network, no database)."""
import os
import sys

import psycopg2
import pytest
from playwright.sync_api import Error as PlaywrightError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import discovery  # noqa: E402
import scraper_v2  # noqa: E402
from scraper_v2 import CONTENT_ATTEMPTS, NotOem, UpdaterV2  # noqa: E402
from writer import Target  # noqa: E402

NAVIGATING = "Page.content: Unable to retrieve content because the page is navigating and changing the content."


class NavigatingPage:
    def __init__(self, busy_reads):
        self.busy_reads = busy_reads
        self.waits = 0
        self.url = "https://example.test/v-2026-x/categories"

    def content(self):
        if self.busy_reads:
            self.busy_reads -= 1
            raise PlaywrightError(NAVIGATING)
        return "<html>ok</html>"

    def wait_for_load_state(self, _state, timeout=None):
        self.waits += 1


def bare_updater(page=None):
    u = object.__new__(UpdaterV2)  # skip __init__: it needs real service URLs
    u._page = page
    return u


def test_content_waits_out_a_self_started_navigation():
    page = NavigatingPage(busy_reads=2)
    assert bare_updater(page)._content() == "<html>ok</html>"
    assert page.waits == 2


def test_content_gives_up_after_the_attempt_limit():
    page = NavigatingPage(busy_reads=CONTENT_ATTEMPTS)
    with pytest.raises(PlaywrightError):
        bare_updater(page)._content()


def test_content_does_not_retry_other_errors():
    class Broken(NavigatingPage):
        def content(self):
            raise PlaywrightError("Target page, context or browser has been closed")
    page = Broken(busy_reads=0)
    with pytest.raises(PlaywrightError):
        bare_updater(page)._content()
    assert page.waits == 0


def test_aftermarket_redirect_is_not_oem_not_a_failure():
    u = bare_updater()
    url = "https://www.moparpartsproonline.com/v-2027-buick-envision--avenir--2-0l-l4-gas"

    def get_page(_url):
        u.last_final_url = url + "/categories?brandType=aftermarket"
        return "<html></html>"
    u.get_page = get_page
    t = Target(1, 1, "2027", "buick", "envision", "avenir", "2-0l-l4-gas", url + "/categories")
    with pytest.raises(NotOem):
        u.crawl(t)
    assert issubclass(NotOem, scraper_v2.NoCatalog)  # the run loop records it as no catalogue


MOPAR = [{"ui": "Buick", "url": "buick"}, {"ui": "Dodge", "url": "dodge", "primary_make": "1"},
         {"ui": "Ram", "url": "ram", "primary_make": "1"}]
TOYOTA = [{"ui": "Chevrolet", "url": "chevrolet"}, {"ui": "Scion", "url": "scion"},
          {"ui": "Subaru", "url": "subaru"}, {"ui": "Toyota", "url": "toyota"}]
GM = [{"ui": "Buick", "url": "buick"}, {"ui": "GMC", "url": "gmc"}]


@pytest.mark.parametrize("config,makes,expected", [
    ("fiat", MOPAR, ["dodge", "ram"]),        # flagged primary makes only
    ("toyota", TOYOTA, ["scion", "toyota"]),  # no flags: named list
    ("gm", GM, ["buick", "gmc"]),             # single-family site: everything
])
def test_oem_makes(config, makes, expected):
    assert [m["url"] for m in discovery.oem_makes(config, makes)] == expected


class FakeCursor:
    """Records SQL; raises uq_trim_name on the lookup insert for one trim."""

    def __init__(self, bad_trim):
        self.bad_trim = bad_trim
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if sql.startswith("INSERT INTO trim") and params[1] == self.bad_trim:
            raise psycopg2.IntegrityError('duplicate key value violates unique constraint "uq_trim_name"')

    def fetchone(self):
        last = self.sql[-1]
        if "RETURNING (xmax = 0)" in last:
            return (True,)
        return None  # lookups: nothing stored yet


def test_discovery_skips_a_vehicle_whose_lookups_conflict_and_carries_on(monkeypatch):
    cur = FakeCursor(bad_trim="empower-plus")

    class Conn:
        def cursor(self):
            return cur

        def commit(self):
            pass

    class Builder:
        ALL_MAKES_URL = "https://example.test/ajax/vehicle-picker/makes/all"
        current_year = 2026
        csrf_token = None

        def __init__(self, *_a, years_to_refresh, **_k):
            self.minimum_year = self.current_year - years_to_refresh + 1

        def _build_params(self, step, *args):
            return (step, args)

        def _fetch_options(self, params, page=None):
            step, args = params
            if len(args) == 2:
                return [{"ui": "Kicks", "url": "kicks"}]
            if len(args) == 3:
                return [{"ui": "Empower+", "url": "empower-plus"}, {"ui": "SV", "url": "sv"}]
            return [{"ui": "1.6L", "url": "1-6l"}]

        def _build_car_url(self, *parts):
            return "https://example.test/v-" + "-".join(map(str, parts))

    class Page:
        def inner_text(self, _sel):
            return '[{"ui": "Nissan", "url": "nissan", "start_year": 1990, "end_year": 2027}]'

        def evaluate(self, _js):
            return None

    class Updater:
        base_url = "https://example.test"
        config_name = "nissan"
        discovery_years = 1
        request_auth = None
        _page = Page()

        def _navigate(self, _url):
            pass

    monkeypatch.setattr(discovery, "RecentTreeBuilder", Builder)
    d = discovery.Discovery(Updater(), Conn(), mfr_id=1, out_of_time=lambda: False)
    assert d.run() is True
    assert d.skipped == 2  # empower-plus in 2027 and 2026
    assert d.found == 2    # sv in both years
    assert "ROLLBACK TO SAVEPOINT vehicle" in cur.sql
