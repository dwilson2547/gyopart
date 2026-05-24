import os
import sys
import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PARTS_DB_URL = "postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange"


@pytest.fixture(scope="session")
def pi_engine():
    engine = create_engine(PARTS_DB_URL)
    yield engine
    engine.dispose()


def test_pg_schema_tables_importable():
    from utils.pg_schema import (
        manufacturer_table, year_table, make_table, model_table,
        trim_table, engine_table, car_table, category_table,
        subcategory_table, diagram_table, image_table, part_table,
        car_parts_table, diagram_parts_table, part_images_table,
        scrape_run_table,
    )
    assert manufacturer_table.name == "manufacturer"
    assert year_table.name == "year"
    assert make_table.name == "make"
    assert car_table.name == "car"
    assert scrape_run_table.name == "scrape_run"


def test_pg_schema_columns_match_db(pi_engine):
    inspector = inspect(pi_engine)
    existing_tables = inspector.get_table_names()
    for tname in ("manufacturer", "year", "make", "model", "trim", "engine",
                  "car", "category", "subcategory", "diagram", "image",
                  "part", "car_parts", "diagram_parts", "part_images"):
        assert tname in existing_tables, f"Table {tname!r} missing from DB"


def test_scrape_run_table_exists(pi_engine):
    inspector = inspect(pi_engine)
    assert "scrape_run" in inspector.get_table_names(), \
        "scrape_run table missing — run migration 001"


from sqlalchemy import select


@pytest.fixture
def pi_conn(pi_engine):
    with pi_engine.begin() as conn:
        yield conn
        conn.rollback()


def test_get_or_create_manufacturer(pi_conn):
    from utils.pg_writer import get_or_create_manufacturer
    mfr_id = get_or_create_manufacturer(pi_conn, "__test_mfr__", "https://test.example.com")
    assert isinstance(mfr_id, int)
    mfr_id2 = get_or_create_manufacturer(pi_conn, "__test_mfr__", "https://test.example.com")
    assert mfr_id == mfr_id2


def test_get_or_create_year(pi_conn):
    from utils.pg_writer import get_or_create_year
    yr_id = get_or_create_year(pi_conn, "1999")
    assert isinstance(yr_id, int)
    assert get_or_create_year(pi_conn, "1999") == yr_id


def test_get_or_create_make(pi_conn):
    from utils.pg_writer import get_or_create_make
    make_id = get_or_create_make(pi_conn, "Ford", "ford")
    assert isinstance(make_id, int)
    assert get_or_create_make(pi_conn, "Ford", "ford") == make_id


def test_get_or_create_model(pi_conn):
    from utils.pg_writer import get_or_create_make, get_or_create_model
    make_id = get_or_create_make(pi_conn, "Ford", "ford")
    model_id = get_or_create_model(pi_conn, "Mustang", make_id, "mustang")
    assert isinstance(model_id, int)
    assert get_or_create_model(pi_conn, "Mustang", make_id, "mustang") == model_id


def test_get_or_create_part(pi_conn):
    from utils.pg_writer import get_or_create_manufacturer, get_or_create_category, get_or_create_part
    mfr_id = get_or_create_manufacturer(pi_conn, "__test_mfr__")
    cat_id = get_or_create_category(pi_conn, "__test_cat__")
    part_id = get_or_create_part(
        pi_conn, part_number="__TEST-999__", url="https://example.com/p",
        manufacturer_id=mfr_id, title="Test Part", category_id=cat_id,
    )
    assert isinstance(part_id, int)
    part_id2 = get_or_create_part(
        pi_conn, part_number="__TEST-999__", url="https://example.com/p",
        manufacturer_id=mfr_id, title="Test Part", category_id=cat_id,
    )
    assert part_id == part_id2


def test_write_car_data_roundtrip(pi_engine):
    from utils.pg_writer import write_car_data, get_or_create_manufacturer
    with pi_engine.begin() as conn:
        mfr_id = get_or_create_manufacturer(conn, "__test_mfr__")

    car_context = {
        "year": "1999",
        "make_url": "__test_mk__",
        "make_name": "__TestMake__",
        "model_url": "__test_mdl__",
        "model_name": "__TestModel__",
        "trim_url": "__test_trm__",
        "trim_name": "__TestTrim__",
        "engine_url": "__test_eng__",
        "engine_name": "__TestEngine__",
        "base_url": "https://example.com/v-1999-test",
    }
    diagrams_data = [
        {
            "diagram_page_url": "https://example.com/cat-page",
            "diagrams": [
                {
                    "img": "test_diag.png",
                    "img_url": "https://example.com/img/test_diag.png",
                    "alt_text": "Test diagram",
                    "category_name": "Brakes",
                    "base_car_url": car_context["base_url"],
                    "category_link": "https://example.com/v-1999-test/brakes/brake-drums",
                    "parts": {"1": ["__TEST-PART-A__"]},
                }
            ],
            "done": True,
            "skipped": False,
        }
    ]
    parts_data = {
        "__TEST-PART-A__": {
            "title": "Test Part A",
            "part_number": "__TEST-PART-A__",
            "url": "https://example.com/p/__TEST-PART-A__",
            "images": [],
            "details": {},
            "skipped": False,
        }
    }

    write_car_data(pi_engine, car_context, diagrams_data, parts_data, mfr_id)

    with pi_engine.connect() as conn:
        from utils.pg_schema import car_table, part_table
        car_row = conn.execute(
            select(car_table.c.id).where(car_table.c.base_url == car_context["base_url"])
        ).one_or_none()
        assert car_row is not None, "Car was not written"

        part_row = conn.execute(
            select(part_table.c.id).where(part_table.c.part_number == "__TEST-PART-A__")
        ).one_or_none()
        assert part_row is not None, "Part was not written"


def test_scraper_imports_no_browser_cache():
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "scraper.py")).read()
    assert "BrowserCache" not in src, "scraper.py must not import BrowserCache"
    assert "BucketUtils" not in src, "scraper.py must not import BucketUtils"
    assert "WebCacheClient" in src, "scraper.py must use WebCacheClient"
    assert "ImgCacheClient" in src, "scraper.py must use ImgCacheClient"
    assert "RequestAuthClient" in src, "scraper.py must use RequestAuthClient"
    assert "write_car_data" in src, "scraper.py must call write_car_data"
