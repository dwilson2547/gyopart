# Phase 2 — Parts-Direct Scraper Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize the parts-direct scraper to replace local file caching (BrowserCache/BucketUtils) with webcache/imgcache services, add request rate limiting via RequestAuthClient, and write structured part/car data directly to the `parts_interchange` Postgres schema in a single scrape pass.

**Architecture:** The V2 scraper (`partsdirectscraperV2.py`) serves as the starting point. A new canonical `scraper.py` replaces it. The Selenium + TreeBuilder + CachedParser core is preserved unchanged. `BrowserCache` (local bz2 files) is replaced by `WebCacheClient`. `BucketUtils` (Minio) is replaced by `ImgCacheClient`. `RequestAuthClient` wraps all Selenium navigations. A new `pg_writer.py` writes structured data to the existing `parts_interchange` Postgres schema using SQLAlchemy Core upserts. A new `scrape_run` table is added to `parts_interchange` via a SQL migration script. JSON state files (tree.json, parts.json) are preserved for run resumability.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x (Core), psycopg2-binary, `dwilson-cache-client==0.1.1`, `dwilson-imgcache-client==0.3.0`, `dwilson-request-auth-client==0.1.3`, PostgreSQL 16

**Key constants:**
- Webcache service: `WEBCACHE_URL` env var, default `http://webcache.scrapestack.local`
- Imgcache service: `IMGCACHE_URL` env var, default `http://imgcache.scrapestack.local`
- Request auth: `REQUEST_AUTH_SERVER_URL` env var, default `request-auth-server.scrapestack.local:9000`
- Parts interchange DB: `PARTS_DATABASE_URL` env var, default `postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange`
- Client name for caching: `"parts_direct"`
- Imgcache bucket: `"parts-direct"`
- Cache max age: 30 days (2_592_000 seconds)

**Parts interchange DB connection (for local testing):**
- URL: `postgresql://parts_user:parts_pass@localhost:5432/parts_interchange`
- This DB already has all historical data loaded by parts-loader-v2

---

## File Structure

```
web_scrapers/parts_direct/singlethreaded-scraper/
├── src/
│   ├── config.py                    CREATE — all env vars in one place
│   ├── scraper.py                   CREATE — modernized scraper (replaces partsdirectscraperV2.py)
│   ├── run.py                       MODIFY — point at scraper.py instead of partsdirectscraperV2
│   ├── requirements.txt             MODIFY — add sqlalchemy, psycopg2-binary
│   ├── utils/
│   │   ├── pg_schema.py             CREATE — SQLAlchemy Core Table definitions for parts_interchange
│   │   ├── pg_writer.py             CREATE — upsert functions + write_car_data() entry point
│   │   ├── BrowserUtil.py           KEEP unchanged
│   │   ├── TreeBuilder.py           KEEP unchanged
│   │   ├── CachedParser.py          KEEP unchanged
│   │   ├── Constants.py             KEEP unchanged
│   │   └── Exceptions.py           KEEP unchanged
│   ├── migrations/
│   │   └── 001_parts_interchange_scrape_run.sql   CREATE — scrape_run DDL
│   └── tests/
│       └── test_phase2.py           CREATE — pg_writer unit tests + cache integration tests
└── (BrowserCache.py, BucketUtils.py left in place, no longer imported)
```

---

## Task 1: Config + requirements

**Files:**
- Create: `web_scrapers/parts_direct/singlethreaded-scraper/src/config.py`
- Modify: `web_scrapers/parts_direct/singlethreaded-scraper/src/requirements.txt`

- [ ] **Step 1: Create config.py**

```python
import os


class Config:
    CLIENT_NAME: str = "parts_direct"
    IMG_BUCKET: str = "parts-direct"

    WEBCACHE_URL: str = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    IMGCACHE_URL: str = os.environ.get("IMGCACHE_URL", "http://imgcache.scrapestack.local")
    IMGCACHE_TIMEOUT: float = float(os.environ.get("IMGCACHE_TIMEOUT", "30.0"))
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(30 * 24 * 3600)))

    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )

    PARTS_DATABASE_URL: str = os.environ.get(
        "PARTS_DATABASE_URL",
        "postgresql://parts_user:parts_pass@localhost:5432/parts_interchange",
    )

    REMOTE_EXECUTOR: str = os.environ.get("remote_executor", "http://localhost:4444/wd/hub")
    CHROME_PROXY: str = os.environ.get("chrome_proxy", "http://192.168.0.240:8118")
    PAGE_REQUEST_DELAY: float = float(os.environ.get("PAGE_REQUEST_DELAY", "3.5"))
```

- [ ] **Step 2: Update requirements.txt** — add new deps at the end:

```
beautifulsoup4==4.11.1
selenium==4.5.0
packaging==21.3
requests_html==0.10.0
stem==1.8.1
Pillow==9.4.0
lxml_html_clean
sqlalchemy>=2.0
psycopg2-binary>=2.9
dwilson-cache-client==0.1.1
dwilson-imgcache-client==0.3.0
dwilson-request-auth-client==0.1.3
httpx>=0.27.0
```

- [ ] **Step 3: Verify imports resolve**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -c "
import os; os.environ['PARTS_DATABASE_URL']='postgresql://x:y@localhost/z'
from config import Config
assert Config.CLIENT_NAME == 'parts_direct'
assert Config.IMG_BUCKET == 'parts-direct'
assert Config.CACHE_MAX_AGE_SECONDS == 2_592_000
print('config ok')
"
```

Expected: `config ok`

---

## Task 2: SQLAlchemy Core schema definitions

**Files:**
- Create: `web_scrapers/parts_direct/singlethreaded-scraper/src/utils/pg_schema.py`

This file mirrors the existing `parts_interchange` Flask-SQLAlchemy models using plain SQLAlchemy Core `Table` objects. It also defines the new `scrape_run` table. Do NOT alter existing table shapes — only add `scrape_run`.

- [ ] **Step 1: Write the failing test**

Create `web_scrapers/parts_direct/singlethreaded-scraper/src/tests/test_phase2.py`:

```python
import pytest
from sqlalchemy import create_engine, inspect, text


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_pg_schema_tables_importable -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'utils.pg_schema'`

- [ ] **Step 3: Create utils/pg_schema.py**

```python
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, MetaData, String, Table, Text,
)

metadata = MetaData()

manufacturer_table = Table("manufacturer", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(300), nullable=False, unique=True),
    Column("base_url", String(300)),
)

year_table = Table("year", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
)

make_table = Table("make", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
    Column("start_year", Integer),
    Column("end_year", Integer),
)

model_table = Table("model", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("select_value", String(120)),
    Column("make_id", Integer, ForeignKey("make.id")),
)

trim_table = Table("trim", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
)

engine_table = Table("engine", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("select_value", String(120)),
)

car_table = Table("car", metadata,
    Column("id", Integer, primary_key=True),
    Column("year_id", Integer, ForeignKey("year.id")),
    Column("make_id", Integer, ForeignKey("make.id")),
    Column("model_id", Integer, ForeignKey("model.id")),
    Column("trim_id", Integer, ForeignKey("trim.id")),
    Column("engine_id", Integer, ForeignKey("engine.id")),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
    Column("car_id", String(200)),
    Column("vehicle_id", String(200)),
    Column("base_url", String(1000)),
)

category_table = Table("category", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
)

subcategory_table = Table("subcategory", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("category_id", Integer, ForeignKey("category.id")),
)

diagram_table = Table("diagram", metadata,
    Column("id", Integer, primary_key=True),
    Column("image_id", Integer, ForeignKey("image.id")),
    Column("category_id", Integer, ForeignKey("category.id")),
    Column("sub_category_id", Integer, ForeignKey("subcategory.id")),
    Column("base_car_url", String(1000)),
    Column("category_url", String(1000)),
)

image_table = Table("image", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100)),
    Column("bucket_path", String(120)),
    Column("url", String(500)),
    Column("alt_text", String(500)),
    Column("saved", Boolean, default=False),
    Column("uploaded", Boolean, default=False),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
)

part_table = Table("part", metadata,
    Column("id", Integer, primary_key=True),
    Column("url", String(500)),
    Column("part_number", String(200)),
    Column("manufacturer_id", Integer, ForeignKey("manufacturer.id")),
    Column("title", String(200)),
    Column("category_id", Integer, ForeignKey("category.id")),
    Column("other_names", Text()),
    Column("description", Text()),
    Column("replaces", Text()),
    Column("positions", Text()),
    Column("notes", Text()),
    Column("msrp", Float()),
    Column("applications", Text()),
    Column("hazmat", Boolean),
)

car_parts_table = Table("car_parts", metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)

diagram_parts_table = Table("diagram_parts", metadata,
    Column("diagram_id", Integer, ForeignKey("diagram.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
    Column("part_index", String(25)),
)

part_images_table = Table("part_images", metadata,
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
    Column("image_id", Integer, ForeignKey("image.id"), primary_key=True),
    Column("part_image_text", String(500)),
)

scrape_run_table = Table("scrape_run", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("manufacturer", String(100), nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("completed_at", DateTime),
    Column("cars_processed", Integer, default=0),
    Column("new_parts", Integer, default=0),
    Column("updated_parts", Integer, default=0),
    Column("success", Boolean, nullable=False, default=False),
    Column("error_message", String(1000)),
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_pg_schema_tables_importable tests/test_phase2.py::test_pg_schema_columns_match_db -v
```

Expected: PASS (both tests pass against live parts_interchange DB)

---

## Task 3: scrape_run migration

**Files:**
- Create: `web_scrapers/parts_direct/singlethreaded-scraper/src/migrations/001_parts_interchange_scrape_run.sql`

- [ ] **Step 1: Write the failing test** — add to `tests/test_phase2.py`:

```python
def test_scrape_run_table_exists(pi_engine):
    inspector = inspect(pi_engine)
    assert "scrape_run" in inspector.get_table_names(), \
        "scrape_run table missing — run migration 001"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_scrape_run_table_exists -v
```

Expected: FAIL — `scrape_run table missing`

- [ ] **Step 3: Create the migration SQL**

Create `migrations/001_parts_interchange_scrape_run.sql`:

```sql
CREATE TABLE IF NOT EXISTS scrape_run (
    id              SERIAL PRIMARY KEY,
    manufacturer    VARCHAR(100) NOT NULL,
    started_at      TIMESTAMP    NOT NULL,
    completed_at    TIMESTAMP,
    cars_processed  INTEGER      NOT NULL DEFAULT 0,
    new_parts       INTEGER      NOT NULL DEFAULT 0,
    updated_parts   INTEGER      NOT NULL DEFAULT 0,
    success         BOOLEAN      NOT NULL DEFAULT FALSE,
    error_message   VARCHAR(1000)
);
```

- [ ] **Step 4: Run the migration against the live DB**

```bash
PGPASSWORD=parts_pass psql -h localhost -p 5432 -U parts_user -d parts_interchange \
  -f /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src/migrations/001_parts_interchange_scrape_run.sql
```

Expected output: `CREATE TABLE`

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_scrape_run_table_exists -v
```

Expected: PASS

---

## Task 4: pg_writer.py

**Files:**
- Create: `web_scrapers/parts_direct/singlethreaded-scraper/src/utils/pg_writer.py`

`pg_writer.py` provides upsert helpers for every table and a top-level `write_car_data()` entry point called by the scraper once per engine config after all parts are processed.

- [ ] **Step 1: Write the failing tests** — add to `tests/test_phase2.py`:

```python
import pytest
from sqlalchemy import create_engine, text, select
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def pi_conn(pi_engine):
    with pi_engine.begin() as conn:
        yield conn
        conn.rollback()   # roll back test writes so they don't pollute the DB


def test_get_or_create_manufacturer(pi_conn):
    from utils.pg_writer import get_or_create_manufacturer
    mfr_id = get_or_create_manufacturer(pi_conn, "__test_mfr__", "https://test.example.com")
    assert isinstance(mfr_id, int)
    # idempotent
    mfr_id2 = get_or_create_manufacturer(pi_conn, "__test_mfr__", "https://test.example.com")
    assert mfr_id == mfr_id2


def test_get_or_create_year(pi_conn):
    from utils.pg_writer import get_or_create_year
    yr_id = get_or_create_year(pi_conn, "2003")
    assert isinstance(yr_id, int)
    assert get_or_create_year(pi_conn, "2003") == yr_id


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
    # idempotent — second call returns same id
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
        "base_url": "https://example.com/v-1999-__test_mk__-__test_mdl__--__test_trm__--__test_eng__",
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
                    "category_link": "https://example.com/v-1999-__test_mk__-__test_mdl__--__test_trm__--__test_eng__/brakes/brake-drums",
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
        from utils.pg_schema import car_table, part_table, car_parts_table
        car_row = conn.execute(
            select(car_table.c.id).where(car_table.c.base_url == car_context["base_url"])
        ).one_or_none()
        assert car_row is not None, "Car was not written"

        part_row = conn.execute(
            select(part_table.c.id).where(part_table.c.part_number == "__TEST-PART-A__")
        ).one_or_none()
        assert part_row is not None, "Part was not written"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_get_or_create_manufacturer -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'utils.pg_writer'`

- [ ] **Step 3: Create utils/pg_writer.py**

```python
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from utils.pg_schema import (
    car_parts_table, car_table, category_table, diagram_parts_table,
    diagram_table, engine_table, image_table, make_table, manufacturer_table,
    model_table, part_images_table, part_table, subcategory_table,
    trim_table, year_table,
)


def get_or_create_manufacturer(conn: Connection, name: str, base_url: str | None = None) -> int:
    stmt = (
        pg_insert(manufacturer_table)
        .values(name=name, base_url=base_url)
        .on_conflict_do_update(index_elements=["name"], set_={"base_url": base_url})
        .returning(manufacturer_table.c.id)
    )
    return conn.execute(stmt).scalar_one()


def get_or_create_year(conn: Connection, name: str) -> int:
    stmt = (
        pg_insert(year_table)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(year_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(year_table.c.id).where(year_table.c.name == name)).scalar_one()


def get_or_create_make(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(make_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(make_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(make_table.c.id).where(make_table.c.name == name)).scalar_one()


def get_or_create_model(conn: Connection, name: str, make_id: int, select_value: str | None = None) -> int:
    existing = conn.execute(
        select(model_table.c.id).where(
            model_table.c.name == name,
            model_table.c.make_id == make_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        model_table.insert().values(name=name, make_id=make_id, select_value=select_value)
        .returning(model_table.c.id)
    ).scalar_one()


def get_or_create_trim(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(trim_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(trim_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(trim_table.c.id).where(trim_table.c.name == name)).scalar_one()


def get_or_create_engine(conn: Connection, name: str, select_value: str | None = None) -> int:
    stmt = (
        pg_insert(engine_table)
        .values(name=name, select_value=select_value)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(engine_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(engine_table.c.id).where(engine_table.c.name == name)).scalar_one()


def get_or_create_car(
    conn: Connection,
    year_id: int, make_id: int, model_id: int, trim_id: int, engine_id: int,
    manufacturer_id: int, base_url: str,
    car_id_str: str | None = None, vehicle_id_str: str | None = None,
) -> int:
    existing = conn.execute(
        select(car_table.c.id).where(car_table.c.base_url == base_url)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        car_table.insert().values(
            year_id=year_id, make_id=make_id, model_id=model_id,
            trim_id=trim_id, engine_id=engine_id, manufacturer_id=manufacturer_id,
            base_url=base_url, car_id=car_id_str, vehicle_id=vehicle_id_str,
        ).returning(car_table.c.id)
    ).scalar_one()


def get_or_create_category(conn: Connection, name: str) -> int:
    stmt = (
        pg_insert(category_table)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(category_table.c.id)
    )
    row = conn.execute(stmt).one_or_none()
    if row:
        return row[0]
    return conn.execute(select(category_table.c.id).where(category_table.c.name == name)).scalar_one()


def get_or_create_subcategory(conn: Connection, name: str, category_id: int) -> int:
    existing = conn.execute(
        select(subcategory_table.c.id).where(
            subcategory_table.c.name == name,
            subcategory_table.c.category_id == category_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        subcategory_table.insert().values(name=name, category_id=category_id)
        .returning(subcategory_table.c.id)
    ).scalar_one()


def get_or_create_part(
    conn: Connection,
    part_number: str, url: str, manufacturer_id: int,
    title: str | None = None, category_id: int | None = None,
    description: str | None = None, msrp: float | None = None,
) -> int:
    existing = conn.execute(
        select(part_table.c.id).where(part_table.c.part_number == part_number)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        part_table.insert().values(
            part_number=part_number, url=url, manufacturer_id=manufacturer_id,
            title=title, category_id=category_id, description=description, msrp=msrp,
        ).returning(part_table.c.id)
    ).scalar_one()


def get_or_create_image(
    conn: Connection,
    name: str, url: str, manufacturer_id: int,
    alt_text: str | None = None, saved: bool = False, uploaded: bool = False,
) -> int:
    existing = conn.execute(
        select(image_table.c.id).where(image_table.c.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        image_table.insert().values(
            name=name, url=url, manufacturer_id=manufacturer_id,
            alt_text=alt_text, saved=saved, uploaded=uploaded,
        ).returning(image_table.c.id)
    ).scalar_one()


def mark_image_uploaded(conn: Connection, image_id: int) -> None:
    conn.execute(
        image_table.update()
        .where(image_table.c.id == image_id)
        .values(saved=True, uploaded=True)
    )


def get_or_create_diagram(
    conn: Connection,
    base_car_url: str, category_url: str,
    image_id: int | None, category_id: int, sub_category_id: int,
) -> int:
    existing = conn.execute(
        select(diagram_table.c.id).where(
            diagram_table.c.base_car_url == base_car_url,
            diagram_table.c.category_url == category_url,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    return conn.execute(
        diagram_table.insert().values(
            base_car_url=base_car_url, category_url=category_url,
            image_id=image_id, category_id=category_id, sub_category_id=sub_category_id,
        ).returning(diagram_table.c.id)
    ).scalar_one()


def link_car_part(conn: Connection, car_id: int, part_id: int) -> None:
    conn.execute(
        pg_insert(car_parts_table)
        .values(car_id=car_id, part_id=part_id)
        .on_conflict_do_nothing()
    )


def link_diagram_part(conn: Connection, diagram_id: int, part_id: int, part_index: str | None = None) -> None:
    conn.execute(
        pg_insert(diagram_parts_table)
        .values(diagram_id=diagram_id, part_id=part_id, part_index=part_index)
        .on_conflict_do_nothing()
    )


def link_part_image(conn: Connection, part_id: int, image_id: int, text: str | None = None) -> None:
    conn.execute(
        pg_insert(part_images_table)
        .values(part_id=part_id, image_id=image_id, part_image_text=text)
        .on_conflict_do_nothing()
    )


def _parse_category_from_url(url: str) -> tuple[str, str]:
    """Extract (category_name, subcategory_name) from a diagram page URL.

    URL pattern: /v-{year}-{make}-{model}--{trim}--{engine}/{category}/{subcategory}
    Falls back to the last two path segments.
    """
    parts = [p for p in url.rstrip("/").split("/") if p]
    if len(parts) >= 2:
        raw_cat = parts[-2].replace("-", " ").title()
        raw_sub = parts[-1].replace("-", " ").title()
    elif len(parts) == 1:
        raw_cat = parts[-1].replace("-", " ").title()
        raw_sub = raw_cat
    else:
        raw_cat, raw_sub = "Unknown", "Unknown"
    return raw_cat, raw_sub


def write_car_data(
    engine: Engine,
    car_context: dict,
    diagrams_data: list,
    parts_data: dict,
    manufacturer_id: int,
) -> None:
    """Write all structured data for one engine config to parts_interchange.

    car_context keys: year, make_url, make_name, model_url, model_name,
                      trim_url, trim_name, engine_url, engine_name, base_url
    diagrams_data: list of parsed_diagrams dicts from process_car_data
    parts_data: {part_number: part_data dict}
    """
    with engine.begin() as conn:
        year_id = get_or_create_year(conn, str(car_context["year"]))
        make_id = get_or_create_make(conn, car_context["make_name"], car_context["make_url"])
        model_id = get_or_create_model(conn, car_context["model_name"], make_id, car_context["model_url"])
        trim_id = get_or_create_trim(conn, car_context["trim_name"], car_context["trim_url"])
        eng_id = get_or_create_engine(conn, car_context["engine_name"], car_context["engine_url"])
        car_id = get_or_create_car(
            conn, year_id, make_id, model_id, trim_id, eng_id,
            manufacturer_id, car_context["base_url"],
        )

        for diagram_page in diagrams_data:
            if diagram_page.get("skipped"):
                continue
            for diagram in diagram_page.get("diagrams", []):
                if diagram.get("skipped"):
                    continue
                category_url = diagram.get("category_link", "")
                cat_name, sub_cat_name = _parse_category_from_url(category_url)
                category_id = get_or_create_category(conn, cat_name)
                sub_category_id = get_or_create_subcategory(conn, sub_cat_name, category_id)

                img_id: int | None = None
                img_name = diagram.get("img", "")
                if img_name:
                    img_url = diagram.get("img_url", "")
                    img_id = get_or_create_image(
                        conn, img_name,
                        "https:" + img_url if img_url.startswith("//") else img_url,
                        manufacturer_id, diagram.get("alt_text"),
                    )

                diagram_id = get_or_create_diagram(
                    conn, diagram.get("base_car_url", ""), category_url,
                    img_id, category_id, sub_category_id,
                )

                for ref_code, part_numbers in diagram.get("parts", {}).items():
                    for pn in part_numbers:
                        pdata = parts_data.get(pn)
                        if not pdata or pdata.get("skipped"):
                            continue
                        part_url = pdata.get("url", "")
                        part_id = get_or_create_part(
                            conn,
                            part_number=pn,
                            url=part_url,
                            manufacturer_id=manufacturer_id,
                            title=pdata.get("title"),
                            category_id=category_id,
                            description=str(pdata.get("details", {})) if pdata.get("details") else None,
                            msrp=pdata.get("msrp"),
                        )
                        link_car_part(conn, car_id, part_id)
                        link_diagram_part(conn, diagram_id, part_id, ref_code)

                        for img_rec in pdata.get("images", []):
                            for slot in ("main", "preview", "thumb"):
                                slot_data = img_rec.get(slot)
                                if not slot_data:
                                    continue
                                raw_img_url = slot_data.get("url", "")
                                full_url = "https:" + raw_img_url if raw_img_url.startswith("//") else raw_img_url
                                fname = full_url.split("/")[-1]
                                if not fname:
                                    continue
                                pi_id = get_or_create_image(
                                    conn, fname, full_url, manufacturer_id,
                                    alt_text=slot_data.get("alt_text"),
                                )
                                link_part_image(conn, part_id, pi_id, slot)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_get_or_create_manufacturer \
    tests/test_phase2.py::test_get_or_create_year \
    tests/test_phase2.py::test_get_or_create_make \
    tests/test_phase2.py::test_get_or_create_model \
    tests/test_phase2.py::test_get_or_create_part \
    tests/test_phase2.py::test_write_car_data_roundtrip \
    -v
```

Expected: all 6 PASS

---

## Task 5: Modernized scraper.py

**Files:**
- Create: `web_scrapers/parts_direct/singlethreaded-scraper/src/scraper.py`

This replaces `partsdirectscraperV2.py`. Key changes:
- `BrowserCache` removed; `WebCacheClient` used for all cache reads/writes
- `BucketUtils` removed; `ImgCacheClient` used for all image storage
- `RequestAuthClient` wraps every Selenium page navigation
- `pg_writer.write_car_data()` called after processing each engine config
- `scrape_run` row opened at start, updated on completion
- `BrowserUtil`, `TreeBuilder`, `CachedParser`, `Configs` kept unchanged

- [ ] **Step 1: Write the failing test** — add to `tests/test_phase2.py`:

```python
def test_scraper_imports_no_browser_cache():
    import importlib.util, sys
    # scraper.py must not import BrowserCache or BucketUtils
    spec = importlib.util.spec_from_file_location(
        "scraper",
        os.path.join(os.path.dirname(__file__), "..", "scraper.py"),
    )
    import ast
    src = open(os.path.join(os.path.dirname(__file__), "..", "scraper.py")).read()
    assert "BrowserCache" not in src, "scraper.py must not import BrowserCache"
    assert "BucketUtils" not in src, "scraper.py must not import BucketUtils"
    assert "WebCacheClient" in src, "scraper.py must use WebCacheClient"
    assert "ImgCacheClient" in src, "scraper.py must use ImgCacheClient"
    assert "RequestAuthClient" in src, "scraper.py must use RequestAuthClient"
    assert "write_car_data" in src, "scraper.py must call write_car_data"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_scraper_imports_no_browser_cache -v
```

Expected: FAIL — `scraper.py` not found

- [ ] **Step 3: Create scraper.py**

```python
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime as dt

from cache_client import WebCacheClient
from imgcache_client import ImgCacheClient
from request_auth_client import RequestAuthClient
from sqlalchemy import create_engine, text

from config import Config
from utils.BrowserUtil import BrowserUtil
from utils.CachedParser import CachedParser
from utils.Configs import Configs
from utils.Constants import keys, PageType, SaveFiles
from utils.Exceptions import (
    NoProgressException, PageRetrievalError, Browser429Error, Browser403Error,
)
from utils.pg_schema import scrape_run_table
from utils.pg_writer import get_or_create_manufacturer, write_car_data
from utils.TreeBuilder import TreeBuilder


class PartsDirectScraper:

    def __init__(self, config_name: str, instance_name: str):
        cfg = Configs.get(config_name)
        self.BASE_URL = cfg["base_url"]
        self.DATA_DIR = cfg["data_dir"]
        self.config_name = config_name
        self.instance_name = instance_name
        self.progress = False
        self.page_request_delay = Config.PAGE_REQUEST_DELAY

        self.PARTS_FILE = os.path.join(self.DATA_DIR, SaveFiles.PARTS_FILE)
        self.TREE_FILE = os.path.join(self.DATA_DIR, SaveFiles.TREE_FILE)
        self.BLANK_TREE = os.path.join(self.DATA_DIR, SaveFiles.BLANK_TREE_FILE)
        self.BACKUPS_DIR = os.path.join(self.DATA_DIR, SaveFiles.BACKUPS_DIR)

        for d in (self.DATA_DIR, self.BACKUPS_DIR):
            os.makedirs(d, exist_ok=True)

        self.cached_parser = CachedParser(self.BASE_URL)
        self.pi_engine = create_engine(Config.PARTS_DATABASE_URL)

    # ── cache helpers ──────────────────────────────────────────────────────────

    def _fetch_and_cache(
        self,
        url: str,
        browser_util: BrowserUtil,
        web_cache: WebCacheClient,
        request_auth: RequestAuthClient,
        retries: int = 0,
    ) -> str:
        if retries > 2:
            raise PageRetrievalError(f"Page retrieval failed after retries: {url}")

        time.sleep(self.page_request_delay)
        domain = self.BASE_URL.split("//")[-1].split("/")[0]
        with request_auth.acquire(domain) as permit:
            browser_util.navigate(url)
            page_source = browser_util.get_page_source()
            permit.set_status(200)

        try:
            if self.cached_parser.check_page(page_source):
                web_cache.store(url, page_source, client_name=Config.CLIENT_NAME)
                self.progress = True
                return page_source
            else:
                return self._fetch_and_cache(url, browser_util, web_cache, request_auth, retries + 1)
        except Browser429Error:
            self.page_request_delay += 0.5
            time.sleep(45)
            return self._fetch_and_cache(url, browser_util, web_cache, request_auth, retries + 1)

    def _get_page(
        self,
        url: str,
        browser_util: BrowserUtil,
        web_cache: WebCacheClient,
        request_auth: RequestAuthClient,
    ) -> str:
        entry = web_cache.get(url, max_age=Config.CACHE_MAX_AGE_SECONDS)
        if entry:
            page_source = entry["content"]
            if not self.cached_parser.check_cached_page(page_source):
                web_cache.delete(entry["content_hash"])
                return self._fetch_and_cache(url, browser_util, web_cache, request_auth)
            return page_source
        return self._fetch_and_cache(url, browser_util, web_cache, request_auth)

    # ── image helpers ──────────────────────────────────────────────────────────

    def _cache_image(self, url: str, img_cache: ImgCacheClient) -> bool:
        if url.startswith("//"):
            url = "https:" + url
        fname = url.split("/")[-1]
        if not fname:
            return False
        meta = img_cache.lookup(url, bucket=Config.IMG_BUCKET)
        if meta:
            return True
        try:
            time.sleep(1)
            with urllib.request.urlopen(url, timeout=30) as resp:
                img_bytes = resp.read()
            img_cache.store(
                url=url, file_bytes=img_bytes,
                client_name=Config.CLIENT_NAME,
                bucket=Config.IMG_BUCKET,
                filename=fname,
            )
            return True
        except Exception as ex:
            print(f"Failed to cache image {url}: {ex}")
            return False

    # ── state helpers ──────────────────────────────────────────────────────────

    def load(self):
        tree = parts = None
        try:
            with open(self.TREE_FILE) as f:
                tree = json.load(f)
        except Exception:
            pass
        try:
            with open(self.PARTS_FILE) as f:
                parts = json.load(f)
        except Exception:
            pass
        return tree, parts

    def save(self, tree, parts, fresh_run: bool = False):
        print("saving...")
        if tree:
            with open(self.TREE_FILE, "w") as f:
                f.write(json.dumps(tree))
            if fresh_run:
                with open(self.BLANK_TREE, "w") as f:
                    f.write(json.dumps(tree))
        if parts:
            with open(self.PARTS_FILE, "w") as f:
                f.write(json.dumps(parts))
        try:
            if os.path.exists(self.TREE_FILE):
                shutil.copyfile(self.TREE_FILE, os.path.join(self.BACKUPS_DIR, SaveFiles.TREE_FILE))
            if os.path.exists(self.PARTS_FILE):
                shutil.copyfile(self.PARTS_FILE, os.path.join(self.BACKUPS_DIR, SaveFiles.PARTS_FILE))
        except Exception as ex:
            print(f"Backup failed: {ex}")
        print("finished")

    # ── scrape_run audit ───────────────────────────────────────────────────────

    def _open_scrape_run(self) -> int:
        with self.pi_engine.begin() as conn:
            row = conn.execute(
                scrape_run_table.insert()
                .values(manufacturer=self.config_name, started_at=dt.utcnow(), success=False)
                .returning(scrape_run_table.c.id)
            )
            return row.scalar_one()

    def _close_scrape_run(self, run_id: int, cars_processed: int, new_parts: int, success: bool, error: str | None = None):
        with self.pi_engine.begin() as conn:
            conn.execute(
                scrape_run_table.update()
                .where(scrape_run_table.c.id == run_id)
                .values(
                    completed_at=dt.utcnow(),
                    cars_processed=cars_processed,
                    new_parts=new_parts,
                    success=success,
                    error_message=error,
                )
            )

    # ── main scrape ────────────────────────────────────────────────────────────

    def scrape(self):
        fresh_run = False
        tree, parts = self.load()

        if not tree:
            fresh_run = True
            tree = TreeBuilder(self.BASE_URL).scrape_car_list()
        if not parts:
            parts = {}

        if fresh_run:
            self.save(tree, parts, fresh_run=True)

        run_id = self._open_scrape_run()
        cars_processed = 0
        new_parts = 0
        try:
            with self.pi_engine.begin() as conn:
                manufacturer_id = get_or_create_manufacturer(
                    conn, self.config_name, self.BASE_URL
                )

            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache, \
                 ImgCacheClient(Config.IMGCACHE_URL, timeout=Config.IMGCACHE_TIMEOUT) as img_cache, \
                 RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL) as request_auth:

                self.traverse_tree(
                    tree, parts, web_cache, img_cache, request_auth,
                    manufacturer_id, run_id,
                    cars_processed_ref=[cars_processed],
                    new_parts_ref=[new_parts],
                )
                cars_processed = cars_processed  # updated by traverse_tree via ref
        except Exception as ex:
            self._close_scrape_run(run_id, cars_processed, new_parts, success=False, error=str(ex)[:1000])
            raise

        self._close_scrape_run(run_id, cars_processed, new_parts, success=True)
        self.save(tree, parts)

    def traverse_tree(
        self, tree, parts, web_cache, img_cache, request_auth,
        manufacturer_id, run_id, cars_processed_ref, new_parts_ref,
    ):
        try:
            for yr in list(tree.keys()):
                year = tree[yr]
                for mk in list(year[keys.MAKES].keys()):
                    make = year[keys.MAKES][mk]
                    for mdl in list(make[keys.MODELS].keys()):
                        model = make[keys.MODELS][mdl]
                        for trm in list(model[keys.TRIMS].keys()):
                            trim = model[keys.TRIMS][trm]
                            for eng in list(trim[keys.ENGINES].keys()):
                                engine = trim[keys.ENGINES][eng]
                                if engine.get("done"):
                                    continue
                                parts_before = len(parts)
                                self.process_car_data(
                                    engine[keys.PAGE_URL], engine, parts,
                                    web_cache, img_cache, request_auth,
                                )
                                engine["done"] = True
                                cars_processed_ref[0] += 1
                                new_parts_ref[0] += len(parts) - parts_before

                                car_context = {
                                    "year": yr,
                                    "make_url": mk,
                                    "make_name": make.get("ui", mk),
                                    "model_url": mdl,
                                    "model_name": model.get("ui", mdl),
                                    "trim_url": trm,
                                    "trim_name": trim.get("ui", trm),
                                    "engine_url": eng,
                                    "engine_name": engine.get("ui", eng),
                                    "base_url": engine[keys.PAGE_URL],
                                }
                                write_car_data(
                                    self.pi_engine,
                                    car_context,
                                    engine.get(keys.DIAGRAMS, []),
                                    parts,
                                    manufacturer_id,
                                )
                                self.save(tree, parts)
        except Exception as ex:
            self.save(tree, parts)
            if not self.progress:
                raise NoProgressException(ex)
            raise
        except KeyboardInterrupt:
            self.save(tree, parts)
            sys.exit()

    def process_car_data(self, url, engine, parts, web_cache, img_cache, request_auth):
        if "categories" in engine:
            engine.pop("categories")
        if keys.PARTS not in engine:
            engine[keys.PARTS] = []
        if keys.DIAGRAMS not in engine:
            engine[keys.DIAGRAMS] = []

        browser_util = BrowserUtil(debug_port="", proxy=Config.CHROME_PROXY)

        if keys.CATEGORY_LINKS not in engine:
            try:
                categories_page = self._get_page(url, browser_util, web_cache, request_auth)
            except PageRetrievalError:
                print(f"Failed to retrieve categories page, skipping. url: {url}")
                engine[keys.CATEGORY_LINKS] = []
                engine["skipped"] = True
                browser_util.close()
                return
            engine[keys.CATEGORY_LINKS] = self.cached_parser.parse_cached_page(
                categories_page, PageType.CATEGORIES
            )

        for category_link in engine[keys.CATEGORY_LINKS]:
            if category_link["done"]:
                continue
            category_url = category_link["url"]

            try:
                diagram_page = self._get_page(category_url, browser_util, web_cache, request_auth)
            except PageRetrievalError:
                print(f"Failed to retrieve diagram page, skipping. url: {category_url}")
                category_link["done"] = True
                category_link["skipped"] = True
                continue

            additional_vars = {"base_car_url": url, "category_page_url": category_url}
            diagrams, part_list = self.cached_parser.parse_cached_page(
                diagram_page, PageType.DIAGRAMS, additional_vars
            )

            for diagram in diagrams["diagrams"]:
                img_url = diagram.get("img_url", "")
                if img_url and diagram.get("img"):
                    full_url = "https:" + img_url if img_url.startswith("//") else img_url
                    ok = self._cache_image(full_url, img_cache)
                    if ok:
                        # Update image record to mark uploaded=True
                        with self.pi_engine.begin() as conn:
                            from utils.pg_schema import image_table
                            from utils.pg_writer import get_or_create_image, mark_image_uploaded
                            img_id = get_or_create_image(
                                conn, diagram["img"], full_url, 0,
                                alt_text=diagram.get("alt_text"),
                            )
                            mark_image_uploaded(conn, img_id)

            engine[keys.DIAGRAMS].append(diagrams)

            for part_number, part_page_url in part_list.items():
                if part_number not in engine[keys.PARTS]:
                    engine[keys.PARTS].append(part_number)

            parts_to_fetch = [
                {"part_number": pn, "url": pu}
                for pn, pu in part_list.items()
                if pn not in parts
            ]
            for part in parts_to_fetch:
                pn = part["part_number"]
                try:
                    part_page = self._get_page(
                        part["url"], browser_util, web_cache, request_auth
                    )
                except PageRetrievalError:
                    parts[pn] = {"title": "", "part_number": pn, "url": part["url"],
                                 "images": [], "details": {}, "skipped": True}
                    continue

                part_data = self.cached_parser.parse_cached_page(part_page, PageType.PART)
                part_data["url"] = part["url"]
                parts[pn] = part_data

                for img_rec in part_data.get("images", []):
                    for slot in ("main", "preview", "thumb"):
                        slot_data = img_rec.get(slot)
                        if not slot_data:
                            continue
                        raw_url = slot_data.get("url", "")
                        full_url = "https:" + raw_url if raw_url.startswith("//") else raw_url
                        self._cache_image(full_url, img_cache)

            category_link["done"] = True

        browser_util.close()
```

- [ ] **Step 4: Run the source-text test to verify it passes**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py::test_scraper_imports_no_browser_cache -v
```

Expected: PASS

- [ ] **Step 5: Verify scraper.py syntax is valid**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -c "import ast; ast.parse(open('scraper.py').read()); print('syntax ok')"
```

Expected: `syntax ok`

---

## Task 6: Update run.py

**Files:**
- Modify: `web_scrapers/parts_direct/singlethreaded-scraper/src/run.py`

The existing `run.py` imports from `partsdirectscraperV2`. Update it to import from `scraper`.

- [ ] **Step 1: Read current run.py**

```bash
cat /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src/run.py
```

Current content:
```python
import sys
import time
from partsdirectscraperV2 import PartsDirectScraper
from utils.Exceptions import NoProgressException, TreeBuilderError, PageRetrievalError, Browser403Error, InternetDownError

if __name__ == '__main__':
    args = sys.argv
    if len(args) != 3:
        print('Expected two arguments (python3 run.py config instance_name), exiting')
        sys.exit(1)

    config_name = args[1]
    instance_name = args[2]

    pds = PartsDirectScraper(config_name, instance_name)

    while True:
        try:
            pds.scrape()
            break
        except NoProgressException as ex:
            print('Stopped making progress, stopping process')
            raise ex
        except Browser403Error as ex:
            print('403 error caught, exiting')
            sys.exit(0)
        except TreeBuilderError as ex:
            print('Tree builder error caught, exiting now')
            sys.exit(0)
        except InternetDownError as ex:
            print('Internet down, pause for 60 seconds and restart')
            time.sleep(60)
        except Exception as ex:
            print(ex)
            time.sleep(60)
```

- [ ] **Step 2: Update the import line**

Change `from partsdirectscraperV2 import PartsDirectScraper` to `from scraper import PartsDirectScraper`.

Final `run.py`:

```python
import sys
import time
from scraper import PartsDirectScraper
from utils.Exceptions import NoProgressException, TreeBuilderError, PageRetrievalError, Browser403Error, InternetDownError

if __name__ == '__main__':
    args = sys.argv
    if len(args) != 3:
        print('Expected two arguments (python3 run.py config instance_name), exiting')
        sys.exit(1)

    config_name = args[1]
    instance_name = args[2]

    pds = PartsDirectScraper(config_name, instance_name)

    while True:
        try:
            pds.scrape()
            break
        except NoProgressException as ex:
            print('Stopped making progress, stopping process')
            raise ex
        except Browser403Error as ex:
            print('403 error caught, exiting')
            sys.exit(0)
        except TreeBuilderError as ex:
            print('Tree builder error caught, exiting now')
            sys.exit(0)
        except InternetDownError as ex:
            print('Internet down, pause for 60 seconds and restart')
            time.sleep(60)
        except Exception as ex:
            print(ex)
            time.sleep(60)
```

- [ ] **Step 3: Verify run.py imports correctly**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -c "import ast; ast.parse(open('run.py').read()); print('syntax ok')"
```

Expected: `syntax ok`

---

## Task 7: Run full test suite

- [ ] **Step 1: Run all Phase 2 tests**

```bash
cd /home/daniel/documents/workspace/web_scrapers/parts_direct/singlethreaded-scraper/src
python3 -m pytest tests/test_phase2.py -v
```

Expected: All tests PASS. The test that checks for scrape_run table existence requires the migration in Task 3 to have been applied.

- [ ] **Step 2: Verify existing junkyard tests still pass (no regressions)**

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory \
    python3 -m pytest tests/ -v
```

Expected: 17 tests PASS, 6 SKIP (parts_interchange tests that skip without env)

---

## Self-Review Checklist

After all tasks complete, verify:

- [ ] `scraper.py` has no import of `BrowserCache` or `BucketUtils`
- [ ] All HTML cache reads go through `web_cache.get(url, max_age=...)`, writes through `web_cache.store(url, html, client_name=...)`
- [ ] All image fetches check `img_cache.lookup(url, bucket=Config.IMG_BUCKET)` before downloading
- [ ] All Selenium navigations are wrapped in `with request_auth.acquire(domain) as permit:`
- [ ] `write_car_data()` is called once per engine config after `process_car_data()` completes
- [ ] `scrape_run` row is opened before traversal and closed (with `success=True/False`) in all code paths
- [ ] `scrape_run_table` DDL matches `pg_schema.py` definition exactly
- [ ] pg_writer functions are all idempotent (repeated calls produce same DB state)
- [ ] `_parse_category_from_url` handles edge cases (empty url, short path)
- [ ] All tests pass against the live parts_interchange DB
