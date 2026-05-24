# Phase 1: Junkyard Scraper Migration to Common Postgres Schema

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all five junkyard scrapers from per-scraper SQLite schemas to the shared Postgres `junkyard_inventory` database using the common models defined in Phase 0.

**Architecture:** Each scraper gets a thin rewrite: its local `models.py` is replaced with a `sys.path.insert` import of `common/models.py`, its SQLite engine is replaced with a Postgres engine from a new `common/db.py`, and yard-specific fields that don't map to canonical Vehicle columns go into the `extras` JSONB column. Single-location scrapers seed their Location row on first run. Multi-location scrapers (Pull-A-Part) already handle dynamic location discovery.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, psycopg2-binary, PostgreSQL 16 (scrape_stack, port 5433 on host), existing `cache_client` and `request_auth_client` libs.

---

## File Map

**New files:**
- `web_scrapers/junkyard_inventory_scrapers/common/db.py` — Postgres engine/session factory; all scrapers import from here instead of building their own engine
- `web_scrapers/junkyard_inventory_scrapers/tests/test_phase1_scrapers.py` — integration smoke tests (real Postgres, `JUNKYARD_DATABASE_URL` required)

**Modified files (scraper-by-scraper):**
- `web_scrapers/junkyard_inventory_scrapers/pic-n-pull/scraper.py` — remove VehicleDetail import/usage; write `trim` and `preview_image_url` directly on Vehicle; switch to `common/db.py`
- `web_scrapers/junkyard_inventory_scrapers/pic-n-pull/config.py` — drop `DB_PATH`; read `JUNKYARD_DATABASE_URL` env var
- `web_scrapers/junkyard_inventory_scrapers/parts-galore/scraper.py` — full rewrite to common models; add `_ensure_location()`; `yard_date→arrival_date`, `yard_row→row`, VIN as `source_key`; pg upsert
- `web_scrapers/junkyard_inventory_scrapers/us_auto_parts_sterling_heights/scraper.py` — common models; `_ensure_location()`; `stock_number` as `source_key`; non-standard fields into `extras` JSONB; pg upsert
- `web_scrapers/junkyard_inventory_scrapers/ryans_pic_a_part/scraper.py` — common models; `_ensure_location()`; `api_id` as `source_key`; `preview_image_url` canonical; `extras` JSONB; pg upsert
- `web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper/scraper.py` — common models; drop Make table; make_lookup dict for Vehicle.make; `source_key="{ticket_id}:{line_id}"`; flat Vehicle for detail fields; `detail_fetched_at IS NULL` instead of `has_details`
- `web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper/config.py` — drop `DB_PATH`; `JUNKYARD_DATABASE_URL` env var; drop stale ScrapeRun field references

---

## Source Identifiers and Dedup Keys

| Scraper | `source` value | `source_key` | Single/Multi location |
|---------|---------------|-------------|----------------------|
| `pic-n-pull` | `"pic_n_pull"` | `str(vehicle["id"])` | Multi (48 locations) |
| `parts-galore` | `"parts_galore"` | VIN | Single |
| `us_auto_parts_sterling_heights` | `"us_auto_supply"` | `stock_number` | Single |
| `ryans_pic_a_part` | `"ryans_pic_a_part"` | `api_id` (_id from ES) | Single |
| `pull_a_part_scraper` | `"pull_a_part"` | `f"{ticket_id}:{line_id}"` | Multi (~50 locations) |

---

## Postgres Connection

`JUNKYARD_DATABASE_URL` env var used by all scrapers.
Local value: `postgresql://scrapestack:@localhost:5433/junkyard_inventory`

The `common/db.py` engine factory is the only place this env var is consumed. Each scraper calls `get_engine()` once at startup.

---

## Task 1: `common/db.py` — Postgres engine/session factory

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/common/db.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_phase1_scrapers.py` (initial)

### Step 1.1: Write the failing test

```python
# tests/test_phase1_scrapers.py
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

from db import get_engine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    return get_engine()


def test_db_engine_connects(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_db_engine_default_url_from_env():
    """get_engine() must raise if JUNKYARD_DATABASE_URL is not set."""
    original = os.environ.pop("JUNKYARD_DATABASE_URL", None)
    try:
        with pytest.raises(KeyError):
            get_engine()
    finally:
        if original is not None:
            os.environ["JUNKYARD_DATABASE_URL"] = original
```

### Step 1.2: Run test to verify it fails

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py -v
```

Expected: `ImportError: cannot import name 'get_engine' from 'db'`

### Step 1.3: Create `common/db.py`

```python
import os

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import Session


def get_engine(url: str | None = None):
    database_url = url or os.environ["JUNKYARD_DATABASE_URL"]
    return _create_engine(database_url)


def get_session(engine) -> Session:
    return Session(engine)
```

Notes:
- No `Base.metadata.create_all()` — Alembic manages schema.
- `os.environ["JUNKYARD_DATABASE_URL"]` raises `KeyError` (not silent None) if unset — this is the intended behavior tested above.

### Step 1.4: Run tests to verify they pass

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py -v
```

Expected: 2 tests PASS.

---

## Task 2: Migrate `pic-n-pull` — remove VehicleDetail, switch to Postgres

Pick-n-Pull already uses `common/models.py` via `sys.path.insert`. The only changes needed:
1. Remove `VehicleDetail` import and all `VehicleDetail` rows — `trim` and `preview_image_url` now go directly on `Vehicle`.
2. Replace the SQLite `create_engine(f"sqlite:///{db_path}")` with `get_engine()` from `common/db.py`.
3. Remove `DB_PATH` from `config.py`.

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/pic-n-pull/scraper.py`
- Modify: `web_scrapers/junkyard_inventory_scrapers/pic-n-pull/config.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_phase1_scrapers.py`

### Step 2.1: Add failing test for pic-n-pull Vehicle insert

```python
# Append to tests/test_phase1_scrapers.py

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pic-n-pull"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))

from models import Vehicle, Location, ScrapeRun  # noqa: E402


def test_pic_n_pull_vehicle_has_trim_and_image_directly(engine):
    """trim and preview_image_url must be columns on Vehicle, not VehicleDetail."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("vehicles")}
    assert "trim" in cols
    assert "preview_image_url" in cols
    # VehicleDetail table must not exist
    assert "vehicle_details" not in inspector.get_table_names()
```

### Step 2.2: Run to verify it passes (it should already, from Phase 0)

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py::test_pic_n_pull_vehicle_has_trim_and_image_directly -v
```

Expected: PASS (schema was created in Phase 0). This test documents the invariant.

### Step 2.3: Update `pic-n-pull/config.py`

Remove the `DB_PATH` attribute and add Postgres URL:

```python
import os
from pathlib import Path


class Config:
    # ── Scraper identity ──────────────────────────────────────────────────────
    SOURCE: str = "pic_n_pull"
    CLIENT_NAME: str = "pic_n_pull_inventory"
    CHAIN: str = "Pick-n-Pull"

    # ── API endpoints ──────────────────────────────────────────────────────────
    BASE_URL: str = "https://www.picknpull.com"
    LOCATIONS_URL: str = f"{BASE_URL}/api/locations/inventory"
    VEHICLE_SEARCH_URL: str = f"{BASE_URL}/api/vehicle/search"
    SEARCH_DISTANCE_MILES: int = 1

    # ── Shared service clients ─────────────────────────────────────────────────
    WEBCACHE_URL: str = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", "3600"))

    # ── HTTP headers ───────────────────────────────────────────────────────────
    HEADERS: dict = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.picknpull.com/check-inventory/vehicle-search",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
```

### Step 2.4: Update `pic-n-pull/scraper.py`

The full rewritten file — key changes marked with `# CHANGED`:

```python
#!/usr/bin/env python3
# Site:     Pick-n-Pull (https://www.picknpull.com/)
# Strategy: ajax-api (public JSON endpoints, no browser required)
# Dedup key: vehicle.id stored as source_key.
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)
# Source identifier: "pic_n_pull"

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy.orm import Session

_HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(_HERE.parent / "common"))

from models import Base, Location, ScrapeRun, Vehicle  # noqa: E402  # CHANGED: no VehicleDetail
from db import get_engine  # noqa: E402  # CHANGED: common db factory
from cache_client import WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402
from config import Config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE = Config.SOURCE
DOMAIN = "www.picknpull.com"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except (ValueError, TypeError):
        return None


def _get_json(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
    params: dict | None = None,
) -> list | dict:
    req = requests.Request("GET", url, params=params).prepare()
    cache_key = req.url
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=Config.HEADERS, params=params, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _sync_locations(http, web_cache, request_auth, db, now) -> list[dict]:
    logger.info("Syncing locations …")
    locations: list[dict] = _get_json(http, web_cache, request_auth, Config.LOCATIONS_URL)
    api_ids: set[str] = {str(loc["id"]) for loc in locations}

    for loc in locations:
        source_loc_id = str(loc["id"])
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
        if obj is None:
            db.add(Location(
                source=SOURCE,
                source_location_id=source_loc_id,
                name=loc.get("listText") or f"{loc.get('city')}, {loc.get('state')}",
                chain=Config.CHAIN,
                city=loc.get("city"),
                state=loc.get("state"),
                zip_code=loc.get("postalCode"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            ))
        else:
            obj.last_seen_at = now
            obj.is_active = True

    db.query(Location).filter(
        Location.source == SOURCE,
        Location.is_active.is_(True),
        ~Location.source_location_id.in_(api_ids),
    ).update({"is_active": False}, synchronize_session="fetch")

    db.commit()
    logger.info("Locations synced: %d active.", len(locations))
    return locations


def _sync_location_inventory(http, web_cache, request_auth, db, api_loc, now):
    zip_code = api_loc["postalCode"]
    source_loc_id = str(api_loc["id"])
    loc_name = api_loc.get("listText", zip_code)

    logger.info("Fetching vehicles for %s (id=%s, zip=%s) …", loc_name, source_loc_id, zip_code)

    results: list[dict] = _get_json(
        http, web_cache, request_auth, Config.VEHICLE_SEARCH_URL,
        params={"zip": zip_code, "distance": Config.SEARCH_DISTANCE_MILES,
                "makeId": "", "modelId": "", "year": ""},
    )

    matched = next(
        (r for r in results if str(r.get("location", {}).get("locationID", "")) == source_loc_id),
        None,
    )
    if matched is None:
        logger.warning("No vehicle-search result for location %s — skipping.", source_loc_id)
        return 0, 0, 0, 0

    api_location_data: dict = matched["location"]
    vehicles: list[dict] = matched.get("vehicles", [])

    loc_obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
    if loc_obj is None:
        logger.error("Location %s not in DB — skipping.", source_loc_id)
        return 0, 0, 0, 0

    if not loc_obj.address:
        loc_obj.address = api_location_data.get("address1") or api_location_data.get("address2")
    if not loc_obj.phone:
        loc_obj.phone = api_location_data.get("publicPhone1")
    if loc_obj.lat is None:
        loc_obj.lat = api_location_data.get("mapLatitude")
    if loc_obj.lng is None:
        loc_obj.lng = api_location_data.get("mapLongitude")
    full_name = api_location_data.get("name", "")
    if full_name and not loc_obj.name.startswith("Pick-n-Pull"):
        loc_obj.name = full_name

    location_db_id: int = loc_obj.id

    existing_vehicles: dict[str, Vehicle] = {
        v.source_key: v
        for v in db.query(Vehicle).filter_by(source=SOURCE, location_id=location_db_id).all()
    }

    current_source_keys: set[str] = set()
    new_count = updated_count = 0

    for v in vehicles:
        source_key = str(v["id"])
        current_source_keys.add(source_key)
        arrival_date = _parse_dt(v.get("dateAdded"))
        image_url: str | None = v.get("imageName") or v.get("smallImage") or None
        existing = existing_vehicles.get(source_key)

        if existing is None:
            db.add(Vehicle(
                location_id=location_db_id,
                source=SOURCE,
                source_key=source_key,
                year=v.get("year"),
                make=v.get("make"),
                model=v.get("model"),
                vin=v.get("vin") or None,
                row=v.get("row"),
                arrival_date=arrival_date,
                color=v.get("color") or None,
                trim=v.get("trim") or None,      # CHANGED: flat on Vehicle
                preview_image_url=image_url,      # CHANGED: flat on Vehicle
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            ))
            new_count += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            if v.get("row"):
                existing.row = v["row"]
            if image_url and existing.preview_image_url != image_url:  # CHANGED: flat on Vehicle
                existing.preview_image_url = image_url
            updated_count += 1

    removed_count = 0
    for source_key, vehicle in existing_vehicles.items():
        if source_key not in current_source_keys and vehicle.is_active:
            vehicle.is_active = False
            removed_count += 1

    db.commit()
    logger.info("  %s: %d in feed  +%d new  ~%d updated  -%d removed",
                loc_name, len(vehicles), new_count, updated_count, removed_count)
    return len(vehicles), new_count, updated_count, removed_count


def main() -> None:
    engine = get_engine()  # CHANGED: Postgres from JUNKYARD_DATABASE_URL
    now = _utcnow()

    with Session(engine) as db:
        run = ScrapeRun(source=SOURCE, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache:
                request_auth = RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL)
                http = requests.Session()

                api_locations = _sync_locations(http, web_cache, request_auth, db, now)

                total_feed = total_new = total_updated = total_removed = 0
                for api_loc in api_locations:
                    feed, new, updated, removed = _sync_location_inventory(
                        http, web_cache, request_auth, db, api_loc, now
                    )
                    total_feed += feed
                    total_new += new
                    total_updated += updated
                    total_removed += removed

            run.completed_at = _utcnow()
            run.total_in_feed = total_feed
            run.new_vehicles = total_new
            run.updated_vehicles = total_updated
            run.removed_vehicles = total_removed
            run.success = True
            db.commit()
            logger.info("Scrape complete — %d locations | %d in feed | +%d new | ~%d updated | -%d removed",
                        len(api_locations), total_feed, total_new, total_updated, total_removed)

        except Exception as exc:
            logger.exception("Scrape failed: %s", exc)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
            sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 2.5: Verify scraper imports without error

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers/pic-n-pull
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -c "import scraper; print('OK')"
```

Expected: `OK` with no import errors.

---

## Task 3: Migrate `parts-galore` to common schema

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/parts-galore/scraper.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_phase1_scrapers.py`

### Step 3.1: Add failing test

```python
# Append to tests/test_phase1_scrapers.py

def test_parts_galore_upsert(engine):
    """parts-galore vehicle should upsert with source='parts_galore' and source_key=VIN."""
    from sqlalchemy.orm import Session
    from models import Location, Vehicle
    import datetime

    SOURCE = "parts_galore"
    VIN = "TESTVIN1234567890"
    now = datetime.datetime.utcnow()

    with Session(engine) as db:
        # Ensure test location exists
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1", name="Parts Galore",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        # Insert test vehicle
        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=VIN,
            year=2005, make="Ford", model="Explorer", vin=VIN,
            arrival_date=datetime.datetime(2024, 1, 15),
            row="C7",
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=VIN).first()
        assert fetched is not None
        assert fetched.make == "Ford"
        assert fetched.row == "C7"
        assert fetched.arrival_date == datetime.datetime(2024, 1, 15)

        # Cleanup
        db.delete(fetched)
        db.commit()
```

### Step 3.2: Run to verify it fails (Location may be missing)

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py::test_parts_galore_upsert -v
```

Expected: FAIL or PASS depending on DB state. (This test is mostly schema validation — it should PASS if Phase 0 is complete.)

### Step 3.3: Rewrite `parts-galore/scraper.py`

Full replacement — uses common models, Postgres, location seed:

```python
#!/usr/bin/env python3
# Site:     Parts Galore (https://parts-galore.com/inventory/)
# Strategy: static-html (full inventory table in initial page HTML)
# Dedup key: VIN (stored as source_key)
# Source identifier: "parts_galore"
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "common"))

from models import Base, Location, ScrapeRun, Vehicle  # noqa: E402
from db import get_engine  # noqa: E402
from cache_client import WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

import os

INVENTORY_URL    = "https://parts-galore.com/inventory/"
INVENTORY_DOMAIN = urlparse(INVENTORY_URL).netloc
SOURCE           = "parts_galore"
CLIENT_NAME      = "parts_galore"

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_yard_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _parse_row(tr) -> dict | None:
    cells = tr.find_all("td")
    if len(cells) < 7:
        return None

    def cell(idx: int) -> str | None:
        text = cells[idx].get_text(strip=True)
        return text or None

    vin = cell(3)
    if not vin:
        return None

    return {
        "vin":          vin,
        "year":         _parse_year(cell(0)),
        "make":         cell(1),
        "model":        cell(2),
        "color":        cell(4),
        "arrival_date": _parse_yard_date(cell(5)),
        "row":          cell(6),
    }


def _ensure_location(db: Session, now: datetime) -> int:
    """Seed the single Parts Galore location row if it doesn't exist. Returns location_id."""
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Parts Galore",
            city=None,
            state=None,
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def fetch_page(session, web_cache, request_auth) -> str:
    entry = web_cache.get(INVENTORY_URL, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.info("Cache hit for inventory page")
        return entry["content"]

    logger.info("Fetching %s", INVENTORY_URL)
    with request_auth.acquire(INVENTORY_DOMAIN) as permit:
        resp = session.get(INVENTORY_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(INVENTORY_URL, resp.text, CLIENT_NAME)
    return resp.text


def parse_inventory(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "alldata"})
    if not table:
        raise ValueError("Inventory table 'alldata' not found — possible selector drift")
    tbody = table.find("tbody")
    if not tbody:
        raise ValueError("No <tbody> in 'alldata' table")

    vehicles, skipped = [], 0
    for tr in tbody.find_all("tr"):
        parsed = _parse_row(tr)
        if parsed:
            vehicles.append(parsed)
        else:
            skipped += 1

    logger.info("Parsed %d vehicles (%d skipped)", len(vehicles), skipped)
    return vehicles


def upsert_vehicles(
    db: Session, location_id: int, vehicles: list[dict], now: datetime
) -> tuple[int, int, int]:
    current_vins = {v["vin"] for v in vehicles}

    existing_vins: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_vins))
        .all()
    }

    new_count = updated_count = 0

    for data in vehicles:
        vin = data["vin"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=vin,
                vin=vin,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                arrival_date=data.get("arrival_date"),
                row=data.get("row"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "color":        data.get("color"),
                    "arrival_date": data.get("arrival_date"),
                    "row":          data.get("row"),
                    "last_seen_at": now,
                    "is_active":    True,
                },
            )
        )
        db.execute(stmt)
        if vin in existing_vins:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_vins))
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        location_id = _ensure_location(db, now)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            html = fetch_page(http, web_cache, request_auth)

        vehicles = parse_inventory(html)

        with Session(engine) as db:
            new_c, updated_c, removed_c = upsert_vehicles(db, location_id, vehicles, now)

        logger.info("Run complete — new=%d  updated=%d  removed=%d  total_in_feed=%d",
                    new_c, updated_c, removed_c, len(vehicles))

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(vehicles)
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

    except SystemExit:
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = "429 rate limit — permanent backoff"
            run.success = False
            db.commit()
        raise

    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
        raise

    finally:
        request_auth.close()


if __name__ == "__main__":
    main()
```

### Step 3.4: Verify import

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers/parts-galore
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -c "import scraper; print('OK')"
```

Expected: `OK`

### Step 3.5: Run full test suite

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/ -v
```

Expected: all tests PASS.

---

## Task 4: Migrate `us_auto_parts_sterling_heights` to common schema

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/us_auto_parts_sterling_heights/scraper.py`

### Step 4.1: Add failing test

```python
# Append to tests/test_phase1_scrapers.py

def test_us_auto_vehicle_extras(engine):
    """us_auto vehicles must store hol_model/reference/vehicle_row/location_string in extras JSONB."""
    from sqlalchemy.orm import Session
    from models import Location, Vehicle
    import datetime

    SOURCE = "us_auto_supply"
    STOCK = "TEST-STOCK-001"
    now = datetime.datetime.utcnow()

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1",
                name="US Auto Supply — Sterling Heights",
                city="Sterling Heights", state="MI",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=STOCK,
            year=2010, make="Chevrolet", model="Silverado", vin="1GCNKPEA2BZ123456",
            mileage=120000,
            extras={"hol_model": "C10", "reference": "REF001",
                    "vehicle_row": "A", "location_string": "Sterling Hts",
                    "last_update": "05/01/2026 10:00:00 AM", "status": "0"},
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=STOCK).first()
        assert fetched.extras["hol_model"] == "C10"
        assert fetched.extras["reference"] == "REF001"
        assert fetched.mileage == 120000

        db.delete(fetched)
        db.commit()
```

### Step 4.2: Run to verify it fails (Vehicle does not have STOCK key yet)

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py::test_us_auto_vehicle_extras -v
```

Expected: PASS (schema validation — extras JSONB exists from Phase 0).

### Step 4.3: Rewrite `us_auto_parts_sterling_heights/scraper.py`

```python
#!/usr/bin/env python3
# Site:     US Auto Supply — Sterling Heights, MI
# Strategy: XML feed (CrushYMS single-request XML inventory)
# Feed URL: http://45.79.157.162/1066_inventory.xml
# Dedup key: STOCKNUMBER stored as source_key
# Source identifier: "us_auto_supply"
# Extras JSONB: hol_model, reference, vehicle_row, location_string, last_update, status
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "common"))

from models import Location, ScrapeRun, Vehicle  # noqa: E402
from db import get_engine  # noqa: E402
from cache_client import WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

XML_FEED_URL            = "http://45.79.157.162/1066_inventory.xml"
XML_FEED_DOMAIN         = urlparse(XML_FEED_URL).netloc
SOURCE                  = "us_auto_supply"
CLIENT_NAME             = "us_auto_supply_sterling_heights"
WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml, text/xml, */*",
}

# XML fields that map directly to canonical Vehicle columns
CANONICAL_FIELDS = {
    "VIN":          "vin",
    "iYEAR":        "year",
    "MAKE":         "make",
    "MODEL":        "model",
    "COLOR":        "color",
    "YARD_IN_DATE": "arrival_date",
    "MILEAGE":      "mileage",
}

# XML fields that go into extras JSONB (yard-specific, not in canonical schema)
EXTRAS_FIELDS = {
    "HOL_MODEL":   "hol_model",
    "REFERENCE":   "reference",
    "VEHICLE_ROW": "vehicle_row",
    "LOCATION":    "location_string",
    "LASTUPDATE":  "last_update",
    "iSTATUS":     "status",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.split(".")[0])
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_asset(asset_el) -> dict | None:
    stock_number = (asset_el.findtext("STOCKNUMBER") or "").strip() or None
    if not stock_number:
        return None

    canonical: dict = {"stock_number": stock_number}
    for xml_tag, field in CANONICAL_FIELDS.items():
        raw = (asset_el.findtext(xml_tag) or "").strip() or None
        if field == "year":
            canonical[field] = _parse_int(raw)
        elif field == "mileage":
            canonical[field] = _parse_int(raw)
        elif field == "arrival_date":
            canonical[field] = _parse_arrival_date(raw)
        else:
            canonical[field] = raw

    extras: dict = {}
    for xml_tag, key in EXTRAS_FIELDS.items():
        raw = (asset_el.findtext(xml_tag) or "").strip() or None
        if raw is not None:
            extras[key] = raw
    canonical["extras"] = extras or None

    return canonical


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="US Auto Supply — Sterling Heights",
            city="Sterling Heights",
            state="MI",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def fetch_xml(session, web_cache, request_auth) -> str:
    entry = web_cache.get(XML_FEED_URL, max_age=3600)
    if entry:
        logger.info("Cache hit for XML feed")
        return entry["content"]
    with request_auth.acquire(XML_FEED_DOMAIN) as permit:
        resp = session.get(XML_FEED_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(XML_FEED_URL, resp.text, CLIENT_NAME)
    return resp.text


def upsert_vehicles(
    db: Session, location_id: int, assets: list[dict], now: datetime
) -> tuple[int, int, int]:
    current_stock_numbers = {d["stock_number"] for d in assets}

    existing_stocks: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_stock_numbers))
        .all()
    }

    new_count = updated_count = 0

    for data in assets:
        stock = data["stock_number"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=stock,
                vin=data.get("vin"),
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                arrival_date=data.get("arrival_date"),
                mileage=data.get("mileage"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "vin":          data.get("vin"),
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "color":        data.get("color"),
                    "arrival_date": data.get("arrival_date"),
                    "mileage":      data.get("mileage"),
                    "extras":       data.get("extras"),
                    "last_seen_at": now,
                    "is_active":    True,
                },
            )
        )
        db.execute(stmt)
        if stock in existing_stocks:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_stock_numbers))
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        location_id = _ensure_location(db, now)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            xml_text = fetch_xml(http, web_cache, request_auth)

        root = ET.fromstring(xml_text)
        all_assets, skipped = [], 0
        for asset_el in root.findall("ASSET"):
            parsed = _parse_asset(asset_el)
            if parsed:
                all_assets.append(parsed)
            else:
                skipped += 1

        logger.info("Parsed %d assets (%d skipped)", len(all_assets), skipped)

        with Session(engine) as db:
            new_c, updated_c, removed_c = upsert_vehicles(db, location_id, all_assets, now)

        logger.info("Run complete — new=%d  updated=%d  removed=%d  total_in_feed=%d",
                    new_c, updated_c, removed_c, len(all_assets))

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(all_assets)
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
        raise

    finally:
        request_auth.close()


if __name__ == "__main__":
    main()
```

### Step 4.4: Verify import

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers/us_auto_parts_sterling_heights
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -c "import scraper; print('OK')"
```

Expected: `OK`

---

## Task 5: Migrate `ryans_pic_a_part` to common schema

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/ryans_pic_a_part/scraper.py`

### Step 5.1: Add failing test

```python
# Append to tests/test_phase1_scrapers.py

def test_ryans_vehicle_extras(engine):
    """ryans vehicles must store inventory_id/name/exterior_color in extras JSONB."""
    from sqlalchemy.orm import Session
    from models import Location, Vehicle
    import datetime

    SOURCE = "ryans_pic_a_part"
    API_ID = "test-es-id-001"
    now = datetime.datetime.utcnow()

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1",
                name="Ryan's Pick-a-Part — Detroit",
                city="Detroit", state="MI",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=API_ID,
            year=2012, make="Honda", model="Accord",
            preview_image_url="https://cdn.example.com/img.jpg",
            extras={"inventory_id": "INV123", "name": "2012 Honda Accord",
                    "exterior_color": "Silver",
                    "added_date_ms": 1714000000000, "api_modified_ms": 1714500000000},
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=API_ID).first()
        assert fetched.extras["exterior_color"] == "Silver"
        assert fetched.preview_image_url == "https://cdn.example.com/img.jpg"

        db.delete(fetched)
        db.commit()
```

### Step 5.2: Run to verify test passes (schema validation)

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py::test_ryans_vehicle_extras -v
```

Expected: PASS.

### Step 5.3: Rewrite `ryans_pic_a_part/scraper.py`

Key changes from the original:
- `sys.path.insert` to `common/`; import from `models` and `db`
- Drop SQLite engine; use `get_engine()`
- Drop `sqlite_insert`; use `pg_insert`
- `api_id` → `source_key`; `preview_image_url` and `vin` go flat on Vehicle
- `extras` JSONB for: `inventory_id`, `name`, `exterior_color`, `added_date_ms`, `api_modified_ms`
- `_ensure_location()` for Ryan's Detroit yard
- `ScrapeRun.source = SOURCE`, `ScrapeRun.location_id = location_id`

```python
#!/usr/bin/env python3
# Site:     Ryan's Pick-a-Part — Detroit, MI
# Strategy: Playwright response interception (autorecycler.io elasticsearch/msearch)
# Dedup key: api_id (_id from ES) stored as source_key
# Source identifier: "ryans_pic_a_part"
# Extras JSONB: inventory_id, name, exterior_color, added_date_ms, api_modified_ms
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Response
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "common"))

from models import Location, ScrapeRun, Vehicle  # noqa: E402
from db import get_engine  # noqa: E402
from cache_client import WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INVENTORY_URL           = "https://app.autorecycler.io/inventory/ryans-pick-a-part-detroit"
SOURCE                  = "ryans_pic_a_part"
CLIENT_NAME             = "ryans_pic_a_part"
WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")

SCROLL_WAIT_S   = 2.5
MAX_IDLE_SCROLLS = 6
SCROLL_INTERVAL_S = 1.5
INVENTORY_CACHE_KEY     = f"{INVENTORY_URL}#full_inventory_scrape"
INVENTORY_CACHE_MAX_AGE = 6 * 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_vehicle_source(src: dict) -> dict | None:
    name = src.get("name_text")
    if not name:
        return None

    parts = name.split(" ", 2)
    year  = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
    make  = parts[1] if len(parts) > 1 else None
    model = parts[2] if len(parts) > 2 else None

    preview = src.get("preview_image_image")
    if preview and preview.startswith("//"):
        preview = "https:" + preview

    canonical = {
        "year":              year,
        "make":              make,
        "model":             model,
        "vin":               src.get("vin_text"),
        "row":               src.get("row_text"),
        "preview_image_url": preview,
    }
    extras = {
        "inventory_id":    src.get("inventory_id_text"),
        "name":            name,
        "exterior_color":  src.get("exterior_color_text"),
        "added_date_ms":   src.get("added_date_date"),
        "api_modified_ms": src.get("Modified Date"),
    }
    canonical["extras"] = {k: v for k, v in extras.items() if v is not None} or None
    return canonical


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Ryan's Pick-a-Part — Detroit",
            city="Detroit",
            state="MI",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def upsert_vehicles(
    db: Session,
    location_id: int,
    pairs: list[tuple[str, dict]],
    now: datetime,
) -> tuple[int, int, int]:
    current_api_ids = {api_id for api_id, _ in pairs}

    existing_ids: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_api_ids))
        .all()
    }

    new_count = updated_count = 0

    for api_id, data in pairs:
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=api_id,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                vin=data.get("vin"),
                row=data.get("row"),
                preview_image_url=data.get("preview_image_url"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "vin":               data.get("vin"),
                    "row":               data.get("row"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
                    "last_seen_at":      now,
                    "is_active":         True,
                },
            )
        )
        db.execute(stmt)
        if api_id in existing_ids:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_api_ids))
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


async def scrape_inventory(web_cache, request_auth) -> list[tuple[str, dict]]:
    cached = web_cache.get(INVENTORY_CACHE_KEY, max_age=INVENTORY_CACHE_MAX_AGE)
    if cached:
        logger.info("Cache hit for full inventory — skipping browser run")
        data = json.loads(cached["content"])
        return [(item["api_id"], item["data"]) for item in data]

    collected: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = await context.new_page()

        async def handle_response(response: Response) -> None:
            if "elasticsearch/msearch" not in response.url:
                return
            try:
                body = await response.body()
                data = json.loads(body)
            except Exception:
                return
            for resp in data.get("responses", []):
                for hit in resp.get("hits", {}).get("hits", []):
                    if hit.get("_type") != "custom.inventorysearch":
                        continue
                    api_id = hit.get("_id")
                    if not api_id:
                        continue
                    parsed = _parse_vehicle_source(hit.get("_source", {}))
                    if parsed is not None:
                        collected[api_id] = parsed

        page.on("response", handle_response)

        domain = "app.autorecycler.io"
        with request_auth.acquire(domain) as permit:
            logger.info("Navigating to inventory page: %s", INVENTORY_URL)
            response = await page.goto(INVENTORY_URL, wait_until="networkidle", timeout=60_000)
            permit.set_status(response.status if response else 200)
        await asyncio.sleep(SCROLL_WAIT_S)

        idle_scroll_count = prev_count = 0
        while idle_scroll_count < MAX_IDLE_SCROLLS:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_WAIT_S + SCROLL_INTERVAL_S)
            current_count = len(collected)
            if current_count == prev_count:
                idle_scroll_count += 1
            else:
                idle_scroll_count = 0
                logger.info("Collected %d vehicles (+%d)", current_count, current_count - prev_count)
            prev_count = current_count

        logger.info("Scroll loop complete. Total collected: %d", len(collected))
        await browser.close()

    result = list(collected.items())
    web_cache.store(
        INVENTORY_CACHE_KEY,
        json.dumps([{"api_id": api_id, "data": data} for api_id, data in result]),
        CLIENT_NAME,
    )
    return result


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        location_id = _ensure_location(db, now)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            pairs = asyncio.run(scrape_inventory(web_cache, request_auth))

        if not pairs:
            raise RuntimeError("No vehicles collected — possible site change or block.")

        with Session(engine) as db:
            new_c, updated_c, removed_c = upsert_vehicles(db, location_id, pairs, now)

        logger.info("Run complete — new=%d  updated=%d  removed=%d  total_in_feed=%d",
                    new_c, updated_c, removed_c, len(pairs))

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(pairs)
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
        sys.exit(1)

    finally:
        request_auth.close()


if __name__ == "__main__":
    main()
```

### Step 5.4: Verify import

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers/ryans_pic_a_part
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -c "import scraper; print('OK')"
```

Expected: `OK`

---

## Task 6: Migrate `pull_a_part_scraper` — most complex

Pull-A-Part has:
- A `Make` table that doesn't exist in common schema → replaced with an in-memory `make_lookup: dict[int, str]`
- A `VehicleDetail` table → fields go flat on `Vehicle`
- `has_details` flag → replaced with `detail_fetched_at IS NULL`
- Per-location dedup key: `source_key = f"{ticket_id}:{line_id}"`
- `source_location_id = str(locationID)` for multi-location
- Extra ScrapeRun fields (`locations_synced`, `makes_synced`, `details_fetched`, `vehicles_added`, `vehicles_removed`) → removed; use canonical fields
- `active` / `first_seen` / `last_seen` field names → `is_active` / `first_seen_at` / `last_seen_at`

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper/scraper.py`
- Modify: `web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper/config.py`

### Step 6.1: Add failing test

```python
# Append to tests/test_phase1_scrapers.py

def test_pull_a_part_source_key_format(engine):
    """PAP vehicles use source_key='{ticket_id}:{line_id}' with extras for PAP-specific IDs."""
    from sqlalchemy.orm import Session
    from models import Location, Vehicle
    import datetime

    SOURCE = "pull_a_part"
    SOURCE_KEY = "987654:12"
    now = datetime.datetime.utcnow()

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="99").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="99",
                name="Pull-A-Part — Test Location",
                chain="Pull-A-Part", city="Atlanta", state="GA",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=SOURCE_KEY,
            year=2008, make="Toyota", model="Camry", vin="4T1BE46K48U123456",
            row="D3",
            trim="LE", engine_cylinders=4, trans_type="A",
            extras={"vin_id": 111, "make_id": 7, "model_id": 42, "vin_decoded_id": 555},
            detail_fetched_at=now,
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=SOURCE_KEY).first()
        assert fetched.extras["make_id"] == 7
        assert fetched.trim == "LE"
        assert fetched.engine_cylinders == 4
        assert fetched.detail_fetched_at is not None

        db.delete(fetched)
        db.commit()
```

### Step 6.2: Run to verify test passes (schema validation)

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/test_phase1_scrapers.py::test_pull_a_part_source_key_format -v
```

Expected: PASS.

### Step 6.3: Update `pull_a_part_scraper/config.py`

Remove `DB_PATH`:

```python
import os


class Config:
    # ── API endpoints ────────────────────────────────────────────────────────
    LOCATIONS_URL: str    = "https://enterpriseservice.pullapart.com/Location"
    LOCATIONS_PARAMS: dict = {"siteTypeID": -1}
    MAKES_URL: str        = "https://inventoryservice.pullapart.com/Make/"
    INVENTORY_URL: str    = "https://inventoryservice.pullapart.com/Vehicle/Search"
    DETAILS_URL: str      = (
        "https://inventoryservice.pullapart.com"
        "/VehicleExtendedInfo/{loc_id}/{ticket_id}/{line_id}"
    )

    # ── Shared service clients ───────────────────────────────────────────────
    SOURCE: str           = "pull_a_part"
    CHAIN: str            = "Pull-A-Part"
    CLIENT_NAME: str      = "pull_a_part_inventory"
    WEBCACHE_URL: str     = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", "3600"))

    HEADERS: dict = {
        "Accept":       "application/json",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
```

### Step 6.4: Rewrite `pull_a_part_scraper/scraper.py`

```python
#!/usr/bin/env python3
# Site:     Pull-A-Part (https://www.pullapart.com/inventory/)
# Strategy: ajax-api (JSON endpoints, no browser required)
# Dedup key: source_key = f"{ticket_id}:{line_id}"
# Source identifier: "pull_a_part"
# Extras JSONB: vin_id, make_id, model_id, vin_decoded_id
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)
#
# Phases:
#   1. Sync locations (Location rows via enterprise API)
#   2. Fetch makes list (build make_lookup dict for Vehicle.make)
#   3. Sync inventory (Vehicle rows; one POST per make across all locations)
#   4. Fetch details (flat Vehicle fields: trim/body_type/engine/etc.)

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "common"))

from models import Location, ScrapeRun, Vehicle  # noqa: E402
from db import get_engine  # noqa: E402
from cache_client import WebCacheClient  # noqa: E402
from request_auth_client import RequestAuthClient  # noqa: E402
from config import Config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE = Config.SOURCE


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except (ValueError, TypeError):
        return None


def _cache_key_for_get(url: str, params: dict | None = None) -> str:
    req = requests.Request("GET", url, params=params).prepare()
    return req.url


def _cache_key_for_post(url: str, payload: dict) -> str:
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{url}#body={payload_str}"


def _get(http, web_cache, request_auth, url, params=None):
    cache_key = _cache_key_for_get(url, params)
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    domain = urlparse(url).netloc
    with request_auth.acquire(domain) as permit:
        resp = http.get(url, headers=Config.HEADERS, params=params, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _post(http, web_cache, request_auth, url, payload):
    cache_key = _cache_key_for_post(url, payload)
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    domain = urlparse(url).netloc
    with request_auth.acquire(domain) as permit:
        resp = http.post(url, json=payload, headers=Config.HEADERS, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _sync_locations(http, web_cache, request_auth, db, now) -> list[int]:
    """Upsert all PAP locations; return list of active API location IDs."""
    logger.info("Syncing locations …")
    data = _get(http, web_cache, request_auth, Config.LOCATIONS_URL, params=Config.LOCATIONS_PARAMS)

    api_ids: set[int] = set()
    for loc in data:
        loc_id = loc["locationID"]
        api_ids.add(loc_id)
        source_loc_id = str(loc_id)

        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
        if obj is None:
            db.add(Location(
                source=SOURCE,
                source_location_id=source_loc_id,
                name=loc.get("name") or loc.get("locationName") or loc.get("locName") or source_loc_id,
                chain=Config.CHAIN,
                address=loc.get("address"),
                city=loc.get("city"),
                state=loc.get("state"),
                zip_code=loc.get("zip") or loc.get("postalCode"),
                phone=loc.get("phone"),
                lat=loc.get("lat") or loc.get("latitude"),
                lng=loc.get("lng") or loc.get("longitude"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            ))
        else:
            obj.last_seen_at = now
            obj.is_active = True

    db.query(Location).filter(
        Location.source == SOURCE,
        Location.is_active.is_(True),
        ~Location.source_location_id.in_([str(i) for i in api_ids]),
    ).update({"is_active": False}, synchronize_session="fetch")

    db.commit()
    active_ids = sorted(api_ids)
    logger.info("Locations synced: %d active.", len(active_ids))
    return active_ids


def _fetch_make_lookup(http, web_cache, request_auth) -> dict[int, str]:
    """Return {makeID: makeName} dict. Not stored in DB — used only for Vehicle.make lookup."""
    logger.info("Fetching makes …")
    data = _get(http, web_cache, request_auth, Config.MAKES_URL)
    lookup = {m["makeID"]: m.get("makeName", "") for m in data}
    logger.info("Makes fetched: %d.", len(lookup))
    return lookup


def _sync_inventory(http, web_cache, request_auth, db, location_ids, make_lookup, run) -> None:
    """Upsert inventory across all locations. One POST per make."""
    logger.info("Syncing inventory — %d makes × %d locations …", len(make_lookup), len(location_ids))
    now = _utcnow()

    # Pre-load all existing vehicle keys (source_key) from DB for fast lookup
    location_db_ids: dict[int, int] = {
        int(loc.source_location_id): loc.id
        for loc in db.query(Location).filter(Location.source == SOURCE, Location.is_active.is_(True)).all()
    }

    existing: dict[str, Vehicle] = {
        v.source_key: v
        for v in db.execute(select(Vehicle).where(Vehicle.source == SOURCE)).scalars().all()
    }

    seen_keys: set[str] = set()
    new_count = 0

    for i, (make_id, make_name) in enumerate(make_lookup.items(), 1):
        payload = {"Locations": location_ids, "MakeID": make_id, "Models": [], "Years": []}
        try:
            data = _post(http, web_cache, request_auth, Config.INVENTORY_URL, payload)
        except requests.HTTPError as exc:
            logger.warning("HTTP error fetching make %s: %s", make_id, exc)
            continue

        for loc_result in data:
            for v in loc_result.get("exact", []) + loc_result.get("other", []):
                ticket_id = v["ticketID"]
                line_id   = v["lineID"]
                loc_id    = v["locID"]
                source_key = f"{ticket_id}:{line_id}"
                seen_keys.add(source_key)

                location_db_id = location_db_ids.get(loc_id)
                if location_db_id is None:
                    continue  # unknown location — synced separately

                if source_key in existing:
                    existing[source_key].last_seen_at = now
                    existing[source_key].is_active = True
                else:
                    new_v = Vehicle(
                        location_id=location_db_id,
                        source=SOURCE,
                        source_key=source_key,
                        year=v.get("modelYear"),
                        make=make_name,
                        model=v.get("modelName"),
                        vin=v.get("vin") or None,
                        row=v.get("row"),
                        arrival_date=_parse_dt(v.get("dateYardOn")),
                        extras={
                            "vin_id":        v.get("vinID"),
                            "make_id":       make_id,
                            "model_id":      v.get("modelID"),
                            "vin_decoded_id": v.get("vinDecodedId"),
                        },
                        is_active=True,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    db.add(new_v)
                    existing[source_key] = new_v
                    new_count += 1

        db.commit()
        if i % 10 == 0:
            logger.info("  … %d/%d makes processed", i, len(make_lookup))

    removed_count = 0
    for source_key, vehicle in existing.items():
        if source_key not in seen_keys and vehicle.is_active:
            vehicle.is_active = False
            removed_count += 1

    db.commit()
    run.new_vehicles     = new_count
    run.removed_vehicles = removed_count
    db.commit()
    logger.info("Inventory sync complete — %d added, %d removed.", new_count, removed_count)


def _fetch_details(http, web_cache, request_auth, db, run) -> None:
    """Fetch VehicleExtendedInfo for new vehicles (detail_fetched_at IS NULL)."""
    vehicles = (
        db.execute(
            select(Vehicle).where(Vehicle.source == SOURCE,
                                  Vehicle.is_active.is_(True),
                                  Vehicle.detail_fetched_at.is_(None))
        ).scalars().all()
    )

    if not vehicles:
        logger.info("No vehicles missing details — skipping detail phase.")
        return

    logger.info("Fetching details for %d new vehicles …", len(vehicles))
    fetched = 0
    now = _utcnow()

    for vehicle in vehicles:
        parts = vehicle.source_key.split(":")
        if len(parts) != 2:
            continue
        ticket_id, line_id = parts

        # Derive loc_id from the location's source_location_id
        loc = db.get(Location, vehicle.location_id)
        loc_id = loc.source_location_id if loc else "0"

        url = Config.DETAILS_URL.format(loc_id=loc_id, ticket_id=ticket_id, line_id=line_id)
        try:
            data = _get(http, web_cache, request_auth, url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 404:
                vehicle.detail_fetched_at = now  # No detail available — mark done to stop retrying
                db.commit()
            else:
                logger.warning("HTTP %s fetching details for %s: %s", status, vehicle.source_key, exc)
            continue
        except Exception as exc:
            logger.warning("Error fetching details for %s: %s", vehicle.source_key, exc)
            continue

        vehicle.trim              = data.get("trim")
        vehicle.vehicle_type      = data.get("vehicleType")
        vehicle.body_type         = data.get("bodyType")
        vehicle.body_sub_type     = data.get("bodySubType")
        vehicle.doors             = data.get("doors")
        vehicle.drive_type        = data.get("driveType")
        vehicle.fuel_type         = data.get("fuelType")
        vehicle.engine_block      = data.get("engineBlock")
        vehicle.engine_cylinders  = data.get("engineCylinders")
        vehicle.engine_size       = data.get("engineSize")
        vehicle.engine_aspiration = data.get("engineAspiration")
        vehicle.trans_type        = data.get("transType")
        vehicle.trans_speeds      = data.get("transSpeeds")
        vehicle.style             = data.get("style")
        vehicle.color             = vehicle.color or data.get("color")
        vehicle.detail_fetched_at = now
        db.commit()

        fetched += 1
        if fetched % 100 == 0:
            logger.info("  … details fetched: %d/%d", fetched, len(vehicles))

    run.updated_vehicles = fetched
    db.commit()
    logger.info("Detail fetch complete — %d fetched.", fetched)


def main() -> None:
    engine = get_engine()
    http = requests.Session()
    request_auth = RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL)
    now = _utcnow()

    with Session(engine) as db:
        run = ScrapeRun(source=SOURCE, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        try:
            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache:
                location_ids = _sync_locations(http, web_cache, request_auth, db, now)
                make_lookup   = _fetch_make_lookup(http, web_cache, request_auth)
                _sync_inventory(http, web_cache, request_auth, db, location_ids, make_lookup, run)
                _fetch_details(http, web_cache, request_auth, db, run)

            run.completed_at  = _utcnow()
            run.total_in_feed = run.new_vehicles + run.updated_vehicles
            run.success       = True
            db.commit()
            logger.info("Scrape run completed successfully.")

        except Exception as exc:
            logger.exception("Scraper failed: %s", exc)
            run.completed_at  = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success       = False
            db.commit()
            raise

        finally:
            request_auth.close()


if __name__ == "__main__":
    main()
```

### Step 6.5: Verify import

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -c "import scraper; print('OK')"
```

Expected: `OK`

---

## Task 7: Run full test suite — all scrapers

### Step 7.1: Run all tests

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" \
  python -m pytest tests/ -v
```

Expected output (all PASS):
```
tests/test_db_foundation.py::test_junkyard_db_is_reachable PASSED
tests/test_db_foundation.py::test_parts_db_is_reachable PASSED
... (16 Phase 0 tests)
tests/test_phase1_scrapers.py::test_db_engine_connects PASSED
tests/test_phase1_scrapers.py::test_db_engine_default_url_from_env PASSED
tests/test_phase1_scrapers.py::test_pic_n_pull_vehicle_has_trim_and_image_directly PASSED
tests/test_phase1_scrapers.py::test_parts_galore_upsert PASSED
tests/test_phase1_scrapers.py::test_us_auto_vehicle_extras PASSED
tests/test_phase1_scrapers.py::test_ryans_vehicle_extras PASSED
tests/test_phase1_scrapers.py::test_pull_a_part_source_key_format PASSED
```

### Step 7.2: Verify each scraper module imports cleanly

```bash
cd /home/daniel/documents/workspace/web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:@localhost:5433/junkyard_inventory" python -c "
import sys
sys.path.insert(0, 'common')
sys.path.insert(0, 'pic-n-pull')
import importlib, importlib.util

for name, path in [
    ('pic_n_pull',    'pic-n-pull/scraper.py'),
    ('parts_galore',  'parts-galore/scraper.py'),
    ('us_auto',       'us_auto_parts_sterling_heights/scraper.py'),
    ('ryans',         'ryans_pic_a_part/scraper.py'),
    ('pull_a_part',   'pull_a_part_scraper/scraper.py'),
]:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f'OK: {path}')
"
```

Expected: 5 lines `OK: ...` with no errors.

---

## Self-Review Checklist

After implementing all tasks:

- [ ] `common/db.py` exists and `get_engine()` reads `JUNKYARD_DATABASE_URL`
- [ ] No scraper builds its own SQLite engine or calls `Base.metadata.create_all()`
- [ ] `VehicleDetail` import removed from all scrapers
- [ ] `trim` and `preview_image_url` written directly to `Vehicle` (not a separate table)
- [ ] All single-location scrapers call `_ensure_location()` on startup
- [ ] `uq_vehicle_source` constraint name used in all `on_conflict_do_update` calls
- [ ] `extras` JSONB populated with yard-specific fields for: us_auto, ryans, pull_a_part
- [ ] PAP: `source_key = f"{ticket_id}:{line_id}"`, make_lookup replaces Make table
- [ ] PAP: `detail_fetched_at IS NULL` replaces `has_details == False`
- [ ] PAP: `ScrapeRun` uses only canonical fields (`new_vehicles`, `updated_vehicles`, `removed_vehicles`, `total_in_feed`, `success`, `error_message`)
- [ ] All `ScrapeRun` rows include `source` field
- [ ] All 7 Phase 1 tests PASS
- [ ] All 16 Phase 0 tests still PASS
