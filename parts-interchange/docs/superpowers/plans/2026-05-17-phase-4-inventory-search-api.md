# Phase 4 — Inventory Search API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI service exposing `GET /inventory/search?car_ids=1,2,3&zip=48093&radius_miles=50` that returns nearby junkyard locations with matching vehicles, sorted by distance.

**Architecture:** Single FastAPI app with three focused modules — Pydantic response models in `models.py`, a pure SQLAlchemy Core haversine query in `search.py`, and route + lifespan wiring in `main.py`. Zip-to-coordinate lookup uses the offline `uszipcode` package (no external API calls). Distance filtering happens in Postgres using a raw haversine expression (no PostGIS required).

**Tech Stack:** FastAPI, Uvicorn, SQLAlchemy 2.x Core (text queries), psycopg2-binary, uszipcode, Pydantic v2, pytest + starlette TestClient

> **User constraint:** NO git commits ever.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `junkyard_platform/inventory_api/__init__.py` | Package marker |
| Create | `junkyard_platform/inventory_api/main.py` | FastAPI app, lifespan, `/inventory/search` route |
| Create | `junkyard_platform/inventory_api/models.py` | Pydantic response models (`VehicleResult`, `LocationResult`, `SearchResponse`) |
| Create | `junkyard_platform/inventory_api/search.py` | `search_inventory()` — haversine SQL query, result assembly |
| Create | `junkyard_platform/inventory_api/requirements.txt` | pinned deps for this service |
| Create | `junkyard_platform/tests/test_inventory_api.py` | Unit tests (mocked) + integration tests (skip if no DB) |

---

### Task 1: Pydantic Response Models

**Files:**
- Create: `junkyard_platform/inventory_api/models.py`
- Create: `junkyard_platform/inventory_api/__init__.py`

- [ ] **Step 1: Write failing test for model serialization**

Create `junkyard_platform/tests/test_inventory_api.py`:

```python
"""Inventory API tests — unit (mocked) and integration (skipped if no DB)."""
import os
import pytest
from inventory_api.models import VehicleResult, LocationResult, SearchResponse

# ── model unit tests ───────────────────────────────────────────────────────


def test_vehicle_result_fields():
    v = VehicleResult(
        vehicle_id=42,
        year=2003,
        make="Honda",
        model="Accord",
        trim="EX",
        row="B14",
        car_id=99,
    )
    assert v.vehicle_id == 42
    assert v.car_id == 99
    assert v.trim == "EX"


def test_location_result_fields():
    v = VehicleResult(vehicle_id=1, year=2000, make="Ford", model="F-150",
                      trim=None, row=None, car_id=5)
    loc = LocationResult(
        location_id=1,
        name="Pick-n-Pull Detroit",
        address="123 Main St",
        city="Detroit",
        state="MI",
        zip_code="48210",
        phone="313-555-0100",
        distance_miles=4.2,
        matching_vehicles=[v],
    )
    assert loc.distance_miles == 4.2
    assert len(loc.matching_vehicles) == 1


def test_search_response_wraps_results():
    resp = SearchResponse(results=[])
    assert resp.results == []
```

- [ ] **Step 2: Run test to see it fail**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_vehicle_result_fields -v
```

Expected: `ModuleNotFoundError: No module named 'inventory_api'`

- [ ] **Step 3: Create `__init__.py`**

Create `junkyard_platform/inventory_api/__init__.py` (empty file).

- [ ] **Step 4: Create `models.py`**

Create `junkyard_platform/inventory_api/models.py`:

```python
from __future__ import annotations
from pydantic import BaseModel


class VehicleResult(BaseModel):
    vehicle_id: int
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    row: str | None
    car_id: int | None


class LocationResult(BaseModel):
    location_id: int
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    distance_miles: float
    matching_vehicles: list[VehicleResult]


class SearchResponse(BaseModel):
    results: list[LocationResult]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_vehicle_result_fields tests/test_inventory_api.py::test_location_result_fields tests/test_inventory_api.py::test_search_response_wraps_results -v
```

Expected: 3 PASSED

---

### Task 2: Search Query (Haversine SQL)

**Files:**
- Create: `junkyard_platform/inventory_api/search.py`

- [ ] **Step 1: Write failing test for search function signature**

Append to `junkyard_platform/tests/test_inventory_api.py`:

```python
from unittest.mock import MagicMock, patch
from inventory_api.search import search_inventory
from inventory_api.models import LocationResult


def _make_db_row(
    location_id=1, name="Pick-n-Pull", address="123 Main", city="Detroit",
    state="MI", zip_code="48210", phone="313-555-0100", distance_miles=4.2,
    vehicle_id=42, year=2003, make="Honda", model="Accord", trim="EX",
    row="B14", car_id=99,
):
    return {
        "location_id": location_id, "name": name, "address": address,
        "city": city, "state": state, "zip_code": zip_code, "phone": phone,
        "distance_miles": distance_miles, "vehicle_id": vehicle_id,
        "year": year, "make": make, "model": model, "trim": trim,
        "row": row, "car_id": car_id,
    }


def test_search_inventory_returns_location_results():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    fake_row = _make_db_row()
    mock_conn.execute.return_value = [fake_row]

    results = search_inventory(
        engine=mock_engine,
        car_ids=[99],
        lat=42.33,
        lng=-83.04,
        radius_miles=50.0,
    )
    assert len(results) == 1
    assert isinstance(results[0], LocationResult)
    assert results[0].location_id == 1
    assert results[0].distance_miles == 4.2
    assert len(results[0].matching_vehicles) == 1


def test_search_inventory_groups_multiple_vehicles_per_location():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    rows = [
        _make_db_row(vehicle_id=10, car_id=1),
        _make_db_row(vehicle_id=20, car_id=2),
    ]
    mock_conn.execute.return_value = rows

    results = search_inventory(
        engine=mock_engine, car_ids=[1, 2], lat=42.33, lng=-83.04, radius_miles=50.0
    )
    assert len(results) == 1
    assert len(results[0].matching_vehicles) == 2


def test_search_inventory_empty_result():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value = []

    results = search_inventory(
        engine=mock_engine, car_ids=[1], lat=42.33, lng=-83.04, radius_miles=50.0
    )
    assert results == []
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_search_inventory_returns_location_results -v
```

Expected: `ImportError: cannot import name 'search_inventory'`

- [ ] **Step 3: Create `search.py`**

Create `junkyard_platform/inventory_api/search.py`:

```python
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.engine import Engine

from inventory_api.models import LocationResult, VehicleResult

_HAVERSINE_SQL = text("""
SELECT *
FROM (
    SELECT
        l.id                AS location_id,
        l.name              AS name,
        l.address           AS address,
        l.city              AS city,
        l.state             AS state,
        l.zip_code          AS zip_code,
        l.phone             AS phone,
        3958.8 * 2 * asin(
            sqrt(
                power(sin(radians(l.lat - :lat) / 2), 2) +
                cos(radians(:lat)) * cos(radians(l.lat)) *
                power(sin(radians(l.lng - :lng) / 2), 2)
            )
        )                   AS distance_miles,
        v.id                AS vehicle_id,
        v.year              AS year,
        v.make              AS make,
        v.model             AS model,
        v.trim              AS trim,
        v.row               AS row,
        v.car_id            AS car_id
    FROM locations l
    JOIN vehicles v ON v.location_id = l.id
    WHERE l.is_active = true
      AND v.is_active = true
      AND l.lat IS NOT NULL
      AND l.lng IS NOT NULL
      AND v.car_id_resolved = true
      AND v.car_id IN :car_ids
) sub
WHERE distance_miles <= :radius_miles
ORDER BY distance_miles ASC
""")


def search_inventory(
    engine: Engine,
    car_ids: list[int],
    lat: float,
    lng: float,
    radius_miles: float,
) -> list[LocationResult]:
    with engine.connect() as conn:
        rows = conn.execute(
            _HAVERSINE_SQL,
            {"lat": lat, "lng": lng, "radius_miles": radius_miles, "car_ids": tuple(car_ids)},
        ).mappings().all()

    locations: dict[int, dict] = {}
    vehicles_by_loc: dict[int, list[VehicleResult]] = defaultdict(list)

    for row in rows:
        loc_id = row["location_id"]
        if loc_id not in locations:
            locations[loc_id] = {
                "location_id": loc_id,
                "name": row["name"],
                "address": row["address"],
                "city": row["city"],
                "state": row["state"],
                "zip_code": row["zip_code"],
                "phone": row["phone"],
                "distance_miles": row["distance_miles"],
            }
        vehicles_by_loc[loc_id].append(VehicleResult(
            vehicle_id=row["vehicle_id"],
            year=row["year"],
            make=row["make"],
            model=row["model"],
            trim=row["trim"],
            row=row["row"],
            car_id=row["car_id"],
        ))

    return [
        LocationResult(**loc_data, matching_vehicles=vehicles_by_loc[loc_id])
        for loc_id, loc_data in locations.items()
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_search_inventory_returns_location_results tests/test_inventory_api.py::test_search_inventory_groups_multiple_vehicles_per_location tests/test_inventory_api.py::test_search_inventory_empty_result -v
```

Expected: 3 PASSED

---

### Task 3: FastAPI App with Lifespan and Route

**Files:**
- Create: `junkyard_platform/inventory_api/main.py`
- Create: `junkyard_platform/inventory_api/requirements.txt`

- [ ] **Step 1: Write failing tests for the HTTP layer**

Append to `junkyard_platform/tests/test_inventory_api.py`:

```python
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient


def _make_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value = []
    return mock_engine


def _get_client():
    from inventory_api.main import app
    return TestClient(app)


def test_search_missing_car_ids_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get("/inventory/search?zip=48093&radius_miles=50")
    assert resp.status_code == 422


def test_search_missing_zip_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get("/inventory/search?car_ids=1,2&radius_miles=50")
    assert resp.status_code == 422


def test_search_invalid_zip_format_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get("/inventory/search?car_ids=1&zip=ABCDE&radius_miles=50")
    assert resp.status_code == 422


def test_search_zip_not_found_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        with patch("inventory_api.main.SearchEngine") as mock_se_cls:
            mock_se = MagicMock()
            mock_se_cls.return_value.__enter__.return_value = mock_se
            mock_se.by_zipcode.return_value = None
            client = _get_client()
            resp = client.get("/inventory/search?car_ids=1&zip=00000&radius_miles=50")
    assert resp.status_code == 422
    assert "zip code not found" in resp.json()["detail"].lower()


def test_search_radius_too_large_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get("/inventory/search?car_ids=1&zip=48093&radius_miles=9999")
    assert resp.status_code == 422


def test_search_too_many_car_ids_returns_422():
    car_ids = ",".join(str(i) for i in range(1, 102))
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get(f"/inventory/search?car_ids={car_ids}&zip=48093&radius_miles=50")
    assert resp.status_code == 422


def test_search_returns_empty_results_when_no_matches():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        with patch("inventory_api.main.SearchEngine") as mock_se_cls:
            mock_se = MagicMock()
            mock_se_cls.return_value.__enter__.return_value = mock_se
            zip_result = MagicMock()
            zip_result.lat = 42.33
            zip_result.lng = -83.04
            mock_se.by_zipcode.return_value = zip_result

            with patch("inventory_api.main.search_inventory", return_value=[]):
                client = _get_client()
                resp = client.get("/inventory/search?car_ids=1,2&zip=48093&radius_miles=50")

    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_search_returns_populated_results():
    loc = LocationResult(
        location_id=1, name="Pick-n-Pull", address="123 Main", city="Detroit",
        state="MI", zip_code="48210", phone="313-555-0100", distance_miles=4.2,
        matching_vehicles=[
            VehicleResult(vehicle_id=42, year=2003, make="Honda",
                          model="Accord", trim="EX", row="B14", car_id=99)
        ],
    )
    with patch("inventory_api.main._engine", _make_mock_engine()):
        with patch("inventory_api.main.SearchEngine") as mock_se_cls:
            mock_se = MagicMock()
            mock_se_cls.return_value.__enter__.return_value = mock_se
            zip_result = MagicMock()
            zip_result.lat = 42.33
            zip_result.lng = -83.04
            mock_se.by_zipcode.return_value = zip_result

            with patch("inventory_api.main.search_inventory", return_value=[loc]):
                client = _get_client()
                resp = client.get("/inventory/search?car_ids=99&zip=48093&radius_miles=50")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["location_id"] == 1
    assert data["results"][0]["distance_miles"] == 4.2
    assert data["results"][0]["matching_vehicles"][0]["car_id"] == 99
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_search_missing_car_ids_returns_422 -v
```

Expected: `ImportError: cannot import name 'app' from 'inventory_api.main'`

- [ ] **Step 3: Create `requirements.txt`**

Create `junkyard_platform/inventory_api/requirements.txt`:

```
fastapi>=0.111
uvicorn[standard]>=0.29
uszipcode>=0.2.4
sqlalchemy>=2.0
psycopg2-binary>=2.9
pydantic>=2.0
httpx>=0.27
```

- [ ] **Step 4: Create `main.py`**

Create `junkyard_platform/inventory_api/main.py`:

```python
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from uszipcode import SearchEngine

from inventory_api.models import SearchResponse
from inventory_api.search import search_inventory

_engine: Engine | None = None

_ZIP_RE = re.compile(r"^\d{5}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(url, pool_pre_ping=True)
    yield
    _engine.dispose()


app = FastAPI(title="Inventory Search API", lifespan=lifespan)


def _parse_car_ids(raw: str) -> list[int]:
    try:
        ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="car_ids must be comma-separated integers")
    if not ids:
        raise HTTPException(status_code=422, detail="car_ids must contain at least 1 value")
    if len(ids) > 100:
        raise HTTPException(status_code=422, detail="car_ids must contain at most 100 values")
    return ids


def _resolve_zip(zip_code: str) -> tuple[float, float]:
    if not _ZIP_RE.match(zip_code):
        raise HTTPException(status_code=422, detail="zip must be a 5-digit string")
    with SearchEngine() as se:
        result = se.by_zipcode(zip_code)
    if not result or result.lat is None or result.lng is None:
        raise HTTPException(status_code=422, detail="zip code not found")
    return result.lat, result.lng


@app.get("/inventory/search", response_model=SearchResponse)
def search(
    car_ids: str = Query(..., description="Comma-separated list of car IDs"),
    zip: str = Query(..., description="5-digit US zip code"),
    radius_miles: float = Query(50.0, ge=1.0, le=500.0, description="Search radius in miles"),
):
    ids = _parse_car_ids(car_ids)
    lat, lng = _resolve_zip(zip)
    results = search_inventory(_engine, ids, lat, lng, radius_miles)
    return SearchResponse(results=results)
```

- [ ] **Step 5: Run all HTTP-layer tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py::test_search_missing_car_ids_returns_422 tests/test_inventory_api.py::test_search_missing_zip_returns_422 tests/test_inventory_api.py::test_search_invalid_zip_format_returns_422 tests/test_inventory_api.py::test_search_zip_not_found_returns_422 tests/test_inventory_api.py::test_search_radius_too_large_returns_422 tests/test_inventory_api.py::test_search_too_many_car_ids_returns_422 tests/test_inventory_api.py::test_search_returns_empty_results_when_no_matches tests/test_inventory_api.py::test_search_returns_populated_results -v
```

Expected: 8 PASSED

---

### Task 4: Integration Tests (Real DB, Skippable)

**Files:**
- Modify: `junkyard_platform/tests/test_inventory_api.py`

- [ ] **Step 1: Write integration tests**

Append to `junkyard_platform/tests/test_inventory_api.py`:

```python
import os
import pytest

_JUNKYARD_URL = os.environ.get("JUNKYARD_DATABASE_URL", "")

skip_no_db = pytest.mark.skipif(
    not _JUNKYARD_URL,
    reason="JUNKYARD_DATABASE_URL not set — skipping integration tests",
)


@skip_no_db
def test_integration_search_returns_200():
    """Smoke test: verifies the endpoint connects and returns a valid response shape."""
    from inventory_api.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/inventory/search?car_ids=1&zip=48093&radius_miles=50")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    for loc in data["results"]:
        assert "location_id" in loc
        assert "distance_miles" in loc
        assert "matching_vehicles" in loc
        assert loc["distance_miles"] <= 50.0
        for v in loc["matching_vehicles"]:
            assert v["car_id"] == 1


@skip_no_db
def test_integration_zip_not_found_returns_422():
    from inventory_api.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/inventory/search?car_ids=1&zip=00000&radius_miles=50")
    assert resp.status_code == 422
    assert "zip code not found" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Run all tests (integration skipped without DB env var)**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_inventory_api.py -v
```

Expected: all unit tests PASSED, integration tests SKIPPED (unless `JUNKYARD_DATABASE_URL` is set)

- [ ] **Step 3: Confirm full test count**

The test file should contain 14+ tests total: 3 model tests, 3 search-query tests, 8 HTTP-layer tests, 2 integration tests.

---

### Task 5: Verify Local Startup

**Files:**
- No new files — just a manual smoke test of the running server

- [ ] **Step 1: Install dependencies**

```bash
cd /home/daniel/documents/workspace/junkyard_platform/inventory_api
pip install -r requirements.txt
```

- [ ] **Step 2: Start the server**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
JUNKYARD_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory" \
  uvicorn inventory_api.main:app --port 8100 --reload
```

Expected: `INFO: Application startup complete.`

- [ ] **Step 3: Hit the endpoint**

```bash
curl -s "http://localhost:8100/inventory/search?car_ids=1&zip=48093&radius_miles=50" | python3 -m json.tool
```

Expected: `{"results": [...]}` — may be empty if no matching vehicles; that is correct behavior.

- [ ] **Step 4: Test 422 on bad zip**

```bash
curl -s "http://localhost:8100/inventory/search?car_ids=1&zip=ABCDE&radius_miles=50"
```

Expected: `{"detail": "zip must be a 5-digit string"}`

- [ ] **Step 5: Test 422 on too many car_ids**

```bash
curl -s "http://localhost:8100/inventory/search?car_ids=$(python3 -c "print(','.join(str(i) for i in range(1,102)))")&zip=48093&radius_miles=50"
```

Expected: `{"detail": "car_ids must contain at most 100 values"}`

---

## Self-Review Checklist

**Spec coverage:**
- [x] `GET /inventory/search?car_ids=...&zip=...&radius_miles=...` — Task 3
- [x] Response shape with `results[]`, `location_id`, `distance_miles`, `matching_vehicles` — Task 1
- [x] uszipcode offline lookup, 422 on zip not found — Task 3
- [x] Haversine in pure Postgres SQL (no PostGIS) — Task 2 (`search.py`)
- [x] Only `is_active=true` locations and vehicles — Task 2 (`WHERE` clause)
- [x] Only vehicles where `car_id IN (requested ids)` — Task 2
- [x] Locations with 0 matching vehicles excluded — Task 2 (JOIN eliminates them)
- [x] Sorted by `distance_miles ASC` — Task 2
- [x] Validation: `car_ids` 1–100 items — Task 3
- [x] Validation: `zip` 5-digit string — Task 3
- [x] Validation: `radius_miles` 1–500, default 50 — Task 3
- [x] DB engine created in lifespan, disposed on shutdown — Task 3
- [x] Unit tests with mocked DB — Tasks 1, 2, 3
- [x] Integration tests (skipped without DB) — Task 4
- [x] Requirements file — Task 3
- [x] Local startup instructions — Task 5

**Placeholder scan:** No TBD, no "similar to above", no missing code blocks.

**Type consistency:** `search_inventory` returns `list[LocationResult]` everywhere it's referenced. `_engine` typed as `Engine | None`, used as `Engine` (FastAPI ensures lifespan runs before requests). `VehicleResult` and `LocationResult` field names match between definition and construction in `search.py`.
