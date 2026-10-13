import pytest
from bs4 import BeautifulSoup

from catalog import ScrapeError, catalog_url, parse_catalog


def test_real_ferrari_table(captured):
    diagram = parse_catalog(captured["html"], captured["source_url"]).diagram
    assert len(diagram.parts) == captured["expected_rows"] == 69
    assert len({p.site_part_id for p in diagram.parts}) == 61
    assert diagram.parts[0].part_number == "278162"
    assert diagram.parts[0].notes == "Not for EU GS, UK"
    assert diagram.model == "458"
    assert diagram.variant_name == "Ferrari 458 Italia"
    assert diagram.image_url.endswith("/6ZUPZJC77T6QNNRW4CF5.gif")
    assert diagram.hotspots
    assert diagram.metadata()["car"]["year"] is None
    assert len([p for p in diagram.parts if p.part_index == "1"]) > 1


def test_variant_and_category_discovery(captured):
    variant = "https://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22"
    categories = parse_catalog(captured["html"], variant).links
    assert len(categories) == 10
    assert variant + "/2551" in categories
    diagrams = parse_catalog(captured["html"], variant + "/2551").links
    assert len(diagrams) == 13
    assert captured["source_url"] in diagrams


def test_preserve_leading_zeros_unknown_prices_and_memberships(captured):
    soup = BeautifulSoup(captured["html"], "html.parser")
    row = soup.select_one("#diagtable tr.diagrow")
    row["data-labelcode"] = "010"
    row.find_all("td", recursive=False)[5].string = "-"
    row.find_all("td", recursive=False)[8].append(BeautifulSoup('<a class="diagenquirepos">Enquire</a>', "html.parser"))
    parsed = parse_catalog(str(soup), captured["source_url"]).diagram
    assert parsed.parts[0].part_index == "010"
    assert parsed.parts[0].price_text == "-"
    assert parsed.parts[0].enquire_only
    assert len(parsed.parts) == 69
    assert "msrp" not in parsed.metadata()


@pytest.mark.parametrize("url", [
    "http://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22",
    "https://scuderiacarparts.com/part-finder/ferrari/458/oe/22",
    "https://www.scuderiacarparts.com.evil.example/part-finder/ferrari/458/oe/22",
    "https://www.scuderiacarparts.com/account/signin/",
    "https://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22?query=1",
    "https://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22/2551/48748/1",
])
def test_reject_non_catalog_urls(url):
    with pytest.raises(ScrapeError):
        catalog_url(url)


@pytest.mark.parametrize("mutation", ["empty", "wrong_vehicle", "missing_image", "missing_column", "wrong_child", "hotspot"])
def test_fail_explicitly_on_drift(captured, mutation):
    soup = BeautifulSoup(captured["html"], "html.parser")
    url = captured["source_url"]
    if mutation == "empty":
        for row in soup.select("#diagtable tr.diagrow"):
            row.decompose()
    elif mutation == "wrong_vehicle":
        soup.select_one('select[aria-label="Select Model Variant"] option[selected]')["value"] = "/part-finder/ferrari/458/oe/999"
    elif mutation == "missing_image":
        soup.select_one(".filter_diagimg").decompose()
    elif mutation == "missing_column":
        soup.select_one("#diagtable tr").find_all(["td", "th"], recursive=False)[2].string = "New heading"
    elif mutation == "wrong_child":
        url = url.rsplit("/", 2)[0]
        soup.select_one('select[aria-label="Select Main OE Parts Main Category"] option')["value"] = "/account/signin/"
    else:
        soup.select_one("a.custom-diaghotspot")["style"] = "left: -1%;"
    with pytest.raises(ScrapeError):
        parse_catalog(str(soup), url)


def test_challenge_is_not_catalog(captured):
    with pytest.raises(ScrapeError, match="access_blocked"):
        parse_catalog("<html><title>Just a moment...</title></html>", captured["source_url"])
