"""Discovery parsers and the variant walk, from part-finder pages captured 2026-10-14."""
import asyncio
import json
from pathlib import Path

import pytest

import discovery
from catalog import BASE_URL, Option, ScrapeError, parse_marques, parse_models, parse_oe_link, parse_variants

PAGES = json.loads((Path(__file__).parent / "fixtures/discovery-pages.json").read_text())
FERRARI = BASE_URL + "/part-finder/ferrari"
F458 = FERRARI + "/458"
R8 = BASE_URL + "/part-finder/audi/r8"
CULLINAN_OE = BASE_URL + "/part-finder/rollsroyce/cullinan/oe"


def html(url):
    return PAGES[url]["html"]


def test_marques_are_the_full_list():
    marques = parse_marques(html(FERRARI), FERRARI)
    assert len(marques) == 28
    assert Option("Rolls Royce", BASE_URL + "/part-finder/rollsroyce") in marques
    assert {m.slug for m in marques} >= {"ferrari", "landrover", "mclaren"}


def test_models_are_the_marques_own():
    models = parse_models(html(FERRARI), FERRARI)
    assert len(models) == 45
    assert models[0] == Option("Ferrari 12Cilindri", F458.replace("458", "12cilindri"))
    assert all(m.url.startswith(FERRARI + "/") for m in models)


def test_a_marque_page_without_models_is_empty_not_drift():
    page = html(FERRARI).replace('aria-label="Select Model"', 'aria-label="gone"')
    assert parse_models(page, FERRARI) == []


def test_challenge_page_is_refused():
    with pytest.raises(ScrapeError, match="access_blocked"):
        parse_models("<html><head><title>Just a moment...</title></head></html>", FERRARI)


def test_oe_product_type():
    assert parse_oe_link(html(F458), F458) == F458 + "/oe"
    assert parse_oe_link(html(R8), R8) is None  # tuning only
    bare = "<html><head><title>Alfa Romeo 4C Tuning Parts</title></head><body></body></html>"
    assert parse_oe_link(bare, R8) is None  # tuning-only page without a product type list


def test_variants():
    variants = parse_variants(html(F458 + "/oe"), F458 + "/oe")
    assert [v.slug for v in variants] == ["164", "22", "165", "166", "167"]
    assert variants[1].name == "Ferrari 458 Italia"


def test_single_variant_model_lists_its_preselected_variant():
    [variant] = parse_variants(html(CULLINAN_OE), CULLINAN_OE)
    assert variant == Option("Rolls Royce Cullinan RR31(2017-2023)", CULLINAN_OE + "/724")


def test_tuning_variants_are_not_oe():
    # The R8 page lists /aftermarket/... submodels in the same variant select.
    with pytest.raises(ScrapeError, match="no OE variants"):
        parse_variants(html(R8), R8)


def test_walk_yields_oe_variants_and_skips_tuning_models_and_land_rover():
    marques = [Option("Ferrari", FERRARI), Option("Land Rover", BASE_URL + "/part-finder/landrover"),
               Option("Audi", BASE_URL + "/part-finder/audi")]
    # START_URL is Ferrari's own marque page, read once for the marque list and once for its models.
    assert discovery.START_URL == FERRARI
    pages = {
        (FERRARI, parse_marques): marques,
        (FERRARI, parse_models): [Option("Ferrari 458", F458)],
        (BASE_URL + "/part-finder/audi", parse_models): [Option("Audi R8", R8)],
        (F458, parse_oe_link): F458 + "/oe",
        (R8, parse_oe_link): None,
        (F458 + "/oe", parse_variants): parse_variants(html(F458 + "/oe"), F458 + "/oe"),
    }
    fetched = []

    async def listing(url, parse, **kw):
        fetched.append(url)
        if url == R8:  # tuning-only models redirect
            assert kw == {"on_redirect": None}
        return pages[(url, parse)]

    async def collect():
        return [v async for v in discovery.oe_variants(listing)]

    found = asyncio.run(collect())
    assert [(v.marque.slug, v.model.slug, v.variant_id) for v in found] == [
        ("ferrari", "458", i) for i in ("164", "22", "165", "166", "167")]
    assert BASE_URL + "/part-finder/landrover" not in fetched


class FakeCursor:
    def __init__(self, manufacturers):
        self.manufacturers = manufacturers
        self.sql = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if "FROM manufacturer" in sql:
            mid = self.manufacturers.get(params[0].lower())
            self._row = (mid,) if mid else None
        elif "INSERT INTO scrape_target" in sql:
            self._row = (True,)

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def commit(self):
        pass


def test_queue_upserts_variants_and_reports_marques_without_a_manufacturer():
    cur = FakeCursor({"ferrari": 7})
    queue = discovery.Queue(FakeConn(cur))
    ferrari, model = Option("Ferrari", FERRARI), Option("Ferrari 458", F458)
    queue.add(discovery.Variant(ferrari, model, Option("Ferrari 458 Italia", F458 + "/oe/22")))
    queue.add(discovery.Variant(Option("Bentley", BASE_URL + "/part-finder/bentley"),
                                Option("Bentley Bentayga", BASE_URL + "/part-finder/bentley/bentayga"),
                                Option("Bentayga", BASE_URL + "/part-finder/bentley/bentayga/oe/9")))
    inserts = [p for s, p in cur.sql if "INSERT INTO scrape_target" in s]
    assert inserts == [(7, "", "ferrari", "458", "22", None, F458 + "/oe/22")]
    assert (queue.found, queue.new, queue.missing_manufacturer) == (1, 1, {"Bentley": 1})
    # one manufacturer lookup per marque
    assert sum("FROM manufacturer" in s for s, _ in cur.sql) == 2


def test_listing_maps_a_redirect_only_when_the_caller_says_what_it_means():
    from unittest.mock import Mock

    from catalog import Redirected
    from scraper import Collector

    class Transport:
        async def fetch(self, url):
            raise Redirected(f"redirected: {url}")

    web_cache = Mock()
    web_cache.get.return_value = None
    collector = Collector(web_cache, None, Transport(), bucket="test", max_age=0)
    collector.robots = Mock(can_fetch=Mock(return_value=True))
    assert asyncio.run(collector.listing(R8, parse_oe_link, on_redirect=None)) is None
    with pytest.raises(Redirected):
        asyncio.run(collector.listing(R8, parse_oe_link))
    web_cache.store.assert_not_called()
