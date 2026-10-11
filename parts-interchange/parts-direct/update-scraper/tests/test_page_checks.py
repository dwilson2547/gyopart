import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bootstrap import ensure_singlethreaded_src_path  # noqa: E402

ensure_singlethreaded_src_path()
from utils.CachedParser import CachedParser  # noqa: E402
from utils.Constants import PageType  # noqa: E402
from utils.Exceptions import SiteUnavailableError  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASE = "https://www.moparpartsproonline.com"


def page(name):
    return open(os.path.join(FIX, name), encoding="utf-8", errors="ignore").read()


def test_maintenance_page_is_unavailable_not_a_page():
    p = CachedParser(BASE)
    with pytest.raises(SiteUnavailableError):
        p.check_page(page("maintenance_page.html"))
    assert p.check_cached_page(page("maintenance_page.html")) is False


def test_real_catalogue_page_passes_and_has_categories():
    p = CachedParser(BASE)
    html = page("catalogue_page.html")
    assert p.check_page(html) is True
    assert p.check_cached_page(html) is True
    cats = p.parse_cached_page(html, PageType.CATEGORIES)
    assert len(cats) > 20


def test_h1_is_checked_even_when_a_title_exists():
    p = CachedParser(BASE)
    html = "<html><title>Mopar Parts</title><body><h1>Page Not Found</h1></body></html>"
    assert p.check_page(html) is False


def test_cloudflare_challenge_is_unavailable():
    p = CachedParser(BASE)
    with pytest.raises(SiteUnavailableError):
        p.check_page("<html><title>Just a moment...</title><body></body></html>")


def test_cloudflare_block_page_is_blocked_not_transient():
    from utils.Exceptions import Browser403Error
    p = CachedParser(BASE)
    html = "<html><title>Attention Required! | Cloudflare</title><body></body></html>"
    with pytest.raises(Browser403Error):
        p.check_page(html)
    assert p.check_cached_page(html) is False


def test_2026_part_page_parses_from_react_islands():
    d = CachedParser(BASE).parse_cached_page(page("part_page_2026.html"), PageType.PART)
    assert not d.get("skipped")
    assert d["title"] == "Vehicle Feature Controls Center Stack - Mopar (68608631AB)"
    assert float(d["msrp"]) == 416.0 and d["also_known_as"] == "Center Stack"
    assert d["superseded_part_numbers"] == "68608631AA"
    assert d["images"] and d["images"][0]["main"]["url"].endswith(".webp")
    from writer import clean_title
    assert clean_title(d["title"], "68608631AB") == "Vehicle Feature Controls Center Stack"
