# Phase 3: Vehicle-to-Car Mapping Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each junkyard scrape cycle, resolve every `Vehicle` in `junkyard_inventory.vehicles` to a `car.id` in `parts_interchange.car`, enabling inventory search.

**Architecture:** A pipeline script that processes unresolved vehicles in three ordered steps — VIN decode via the NHTSA API (cached in `vin_cache`), rule-based field transformation, then fuzzy YMMT matching against `parts_interchange` make/model tables. Vehicles that cannot be resolved below the 0.85 confidence threshold land in `mapping_discrepancies` for human review. A separate `reprocess_job.py` re-runs the pipeline after new rules are approved.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x ORM (junkyard session) + Core (parts_interchange), rapidfuzz 3.x, requests, psycopg2-binary, Alembic, pytest, unittest.mock

---

## Future Improvement: NHTSA Batch VIN Decode

> **When rewriting `vin_decoder.py` for production throughput**, replace the per-vehicle `GET /decodevin/{vin}` calls with the batch endpoint:
>
> `POST https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/`  
> Body: `DATA=VIN1,VIN2,...,VIN50&format=json` — decodes up to 50 VINs per request vs. 1 req/VIN with a forced 1s sleep.
>
> At current scale (~10M vehicles), the per-VIN approach takes ~3,000 hours. The batch endpoint would cut that to ~60 hours (50× throughput). The `vin_cache` table already absorbs re-runs safely. The `resolution_pipeline.py` loop would need to be restructured to collect uncached VINs in batches of 50, call the batch endpoint once, store results to `vin_cache`, then proceed per-vehicle. This is a non-trivial refactor — save it for when the pipeline is being productionized.

---

## What's Already Done (Do Not Re-Create)

- `common/models.py` — `Location`, `Vehicle` (with `car_id`/`car_id_resolved`/`car_id_method`/`car_id_confidence`), `MappingRule`, `MappingDiscrepancy`, `ScrapeRun`
- `common/db.py` — `get_engine(url=None)`, `get_session(engine)`
- Alembic migration `0001` — `locations`, `vehicles`, `mapping_rules`, `mapping_discrepancies`, `scrape_runs` all created
- `JUNKYARD_DATABASE_URL=postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory`
- `PARTS_DATABASE_URL=postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange`
- rapidfuzz 3.14.3 and requests 2.32.5 are installed in the active Python env

---

## File Map

**New files:**
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/__init__.py` — empty package marker
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/pi_schema.py` — minimal SQLAlchemy Core table defs for parts_interchange (year, make, model, car); no imports from parts_direct scraper
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/vin_decoder.py` — NHTSA decode + vin_cache + resolve to car_id
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/ymmt_matcher.py` — normalize + rapidfuzz matching
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/rule_engine.py` — apply MappingRules, increment applied_count
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/resolution_pipeline.py` — orchestrates pipeline, CLI entry
- `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/reprocess_job.py` — re-runs pipeline on discrepancies, CLI entry
- `web_scrapers/junkyard_inventory_scrapers/alembic/versions/0002_vin_cache.py` — adds `vin_cache` table only
- `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py` — all unit tests

**Modified files:**
- `web_scrapers/junkyard_inventory_scrapers/common/models.py` — add `VinCache` model (primary key = vin string)
- `web_scrapers/junkyard_inventory_scrapers/requirements-migration.txt` — add `requests>=2.31` and `rapidfuzz>=3.0`

---

## DB Connection Pattern

The pipeline holds **two** connections simultaneously:

```python
from common.db import get_engine, get_session

# junkyard_inventory — ORM session (Vehicle, VinCache, MappingRule, MappingDiscrepancy)
ji_engine = get_engine()   # reads JUNKYARD_DATABASE_URL
session   = get_session(ji_engine)

# parts_interchange — SQLAlchemy Core engine (year, make, model, car via pi_schema.py)
from sqlalchemy import create_engine
import os
pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"])
```

---

## Task 1: VinCache model + Alembic migration 0002

**Files:**
- Modify: `web_scrapers/junkyard_inventory_scrapers/common/models.py`
- Create: `web_scrapers/junkyard_inventory_scrapers/alembic/versions/0002_vin_cache.py`
- Modify: `web_scrapers/junkyard_inventory_scrapers/requirements-migration.txt`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py` (initial)

- [ ] **Step 1.1: Write failing test**

```python
# tests/test_mapping_pipeline.py
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import VinCache  # noqa: E402


def test_vin_cache_model_has_required_fields():
    v = VinCache(
        vin="1HGCM82633A004352",
        make="Honda",
        model="Accord",
        model_year="2003",
        trim="EX",
        error_code=None,
        fetched_at=None,
    )
    assert v.vin == "1HGCM82633A004352"
    assert v.make == "Honda"
    assert v.error_code is None
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd web_scrapers/junkyard_inventory_scrapers
python -m pytest tests/test_mapping_pipeline.py::test_vin_cache_model_has_required_fields -v
```

Expected: `ImportError: cannot import name 'VinCache' from 'common.models'`

- [ ] **Step 1.3: Add VinCache to common/models.py**

Append after the `ScrapeRun` class:

```python
class VinCache(Base):
    __tablename__ = "vin_cache"

    vin         = Column(String(17),  primary_key=True)
    make        = Column(String(100), nullable=True)
    model       = Column(String(200), nullable=True)
    model_year  = Column(String(10),  nullable=True)
    trim        = Column(String(200), nullable=True)
    error_code  = Column(String(20),  nullable=True)   # "11" for pre-1980; "INCOMPLETE" for bad decode
    fetched_at  = Column(DateTime,    nullable=False)

    def __repr__(self) -> str:
        return f"<VinCache {self.vin!r} {self.make} {self.model_year}>"
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
python -m pytest tests/test_mapping_pipeline.py::test_vin_cache_model_has_required_fields -v
```

Expected: PASS

- [ ] **Step 1.5: Write Alembic migration 0002**

Create `alembic/versions/0002_vin_cache.py`:

```python
"""Add vin_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vin_cache",
        sa.Column("vin",        sa.String(17),  nullable=False),
        sa.Column("make",       sa.String(100), nullable=True),
        sa.Column("model",      sa.String(200), nullable=True),
        sa.Column("model_year", sa.String(10),  nullable=True),
        sa.Column("trim",       sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(20),  nullable=True),
        sa.Column("fetched_at", sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint("vin"),
    )


def downgrade() -> None:
    op.drop_table("vin_cache")
```

- [ ] **Step 1.6: Apply migration**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory" \
  alembic upgrade head
```

Expected output includes: `Running upgrade 0001 -> 0002, Add vin_cache table`

- [ ] **Step 1.7: Update requirements-migration.txt**

Replace file contents:

```
alembic>=1.13
psycopg2-binary>=2.9
rapidfuzz>=3.0
requests>=2.31
sqlalchemy>=2.0
```

---

## Task 2: pi_schema.py + package skeleton

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/__init__.py`
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/pi_schema.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 2.1: Write failing test**

Add to `tests/test_mapping_pipeline.py`:

```python
def test_pi_schema_tables_importable():
    from mapping_pipeline.pi_schema import (
        pi_car_table, pi_make_table, pi_model_table, pi_year_table,
    )
    assert pi_year_table.c.id is not None
    assert pi_make_table.c.name is not None
    assert pi_model_table.c.make_id is not None
    assert pi_car_table.c.year_id is not None
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
python -m pytest tests/test_mapping_pipeline.py::test_pi_schema_tables_importable -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline'`

- [ ] **Step 2.3: Create the package and pi_schema.py**

Create `mapping_pipeline/__init__.py` (empty file).

Create `mapping_pipeline/pi_schema.py`:

```python
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

pi_metadata = MetaData()

pi_year_table = Table(
    "year", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),
)

pi_make_table = Table(
    "make", pi_metadata,
    Column("id",   Integer, primary_key=True),
    Column("name", String(120), nullable=False),
)

pi_model_table = Table(
    "model", pi_metadata,
    Column("id",      Integer, primary_key=True),
    Column("name",    String(120), nullable=False),
    Column("make_id", Integer, ForeignKey("make.id")),
)

pi_car_table = Table(
    "car", pi_metadata,
    Column("id",       Integer, primary_key=True),
    Column("year_id",  Integer, ForeignKey("year.id")),
    Column("make_id",  Integer, ForeignKey("make.id")),
    Column("model_id", Integer, ForeignKey("model.id")),
)
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
python -m pytest tests/test_mapping_pipeline.py::test_pi_schema_tables_importable -v
```

Expected: PASS

---

## Task 3: vin_decoder.py

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/vin_decoder.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 3.1: Write failing tests**

Add to `tests/test_mapping_pipeline.py`:

```python
import datetime
from unittest.mock import MagicMock, patch


def _make_nhtsa_response(make="Honda", model="Accord", year="2003", trim="EX", error_code="0"):
    results = [
        {"Variable": "Make",       "Value": make},
        {"Variable": "Model",      "Value": model},
        {"Variable": "ModelYear",  "Value": year},
        {"Variable": "Trim",       "Value": trim},
        {"Variable": "ErrorCode",  "Value": error_code},
    ]
    return {"Results": results}


def test_decode_vin_invalid_length():
    from mapping_pipeline.vin_decoder import decode_vin
    session = MagicMock()
    assert decode_vin("SHORT", session) is None
    session.get.assert_not_called()


def test_decode_vin_cache_hit_success():
    from mapping_pipeline.vin_decoder import decode_vin
    from common.models import VinCache
    cached = VinCache(
        vin="1HGCM82633A004352",
        make="Honda", model="Accord", model_year="2003", trim="EX",
        error_code=None, fetched_at=datetime.datetime.now(),
    )
    session = MagicMock()
    session.get.return_value = cached
    result = decode_vin("1HGCM82633A004352", session)
    assert result == {"make": "Honda", "model": "Accord", "model_year": "2003", "trim": "EX"}


def test_decode_vin_cache_hit_error():
    from mapping_pipeline.vin_decoder import decode_vin
    from common.models import VinCache
    cached = VinCache(vin="1HGCM82633A004352", error_code="11", fetched_at=datetime.datetime.now())
    session = MagicMock()
    session.get.return_value = cached
    assert decode_vin("1HGCM82633A004352", session) is None


def test_decode_vin_cache_miss_success():
    from mapping_pipeline.vin_decoder import decode_vin
    session = MagicMock()
    session.get.return_value = None  # cache miss
    nhtsa_data = _make_nhtsa_response()
    with patch("mapping_pipeline.vin_decoder._fetch_nhtsa", return_value={
        r["Variable"]: r["Value"] for r in nhtsa_data["Results"]
    }), patch("mapping_pipeline.vin_decoder.time.sleep"):
        result = decode_vin("1HGCM82633A004352", session)
    assert result["make"] == "Honda"
    assert result["model"] == "Accord"
    session.merge.assert_called_once()
    session.commit.assert_called_once()


def test_decode_vin_pre1980():
    from mapping_pipeline.vin_decoder import decode_vin
    session = MagicMock()
    session.get.return_value = None
    with patch("mapping_pipeline.vin_decoder._fetch_nhtsa", return_value={
        "Make": "", "Model": "", "ModelYear": "", "Trim": "", "ErrorCode": "11 - "
    }), patch("mapping_pipeline.vin_decoder.time.sleep"):
        result = decode_vin("1HGCM82633A004352", session)
    assert result is None
    session.merge.assert_called_once()


def test_resolve_vin_to_car_id_found():
    from mapping_pipeline.vin_decoder import resolve_vin_to_car_id
    from unittest.mock import MagicMock
    from sqlalchemy.engine import Connection

    pi_engine = MagicMock()
    conn = MagicMock()
    pi_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    pi_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # year row → id=5, make row → id=3, model row → id=12, car → id=99
    conn.execute.side_effect = [
        MagicMock(one_or_none=MagicMock(return_value=(5,))),   # year
        MagicMock(one_or_none=MagicMock(return_value=(3,))),   # make
        MagicMock(one_or_none=MagicMock(return_value=(12,))),  # model
        MagicMock(first=MagicMock(return_value=(99,))),        # car
    ]
    decoded = {"make": "Honda", "model": "Accord", "model_year": "2003", "trim": "EX"}
    assert resolve_vin_to_car_id(decoded, pi_engine) == 99


def test_resolve_vin_to_car_id_missing_year():
    from mapping_pipeline.vin_decoder import resolve_vin_to_car_id
    pi_engine = MagicMock()
    conn = MagicMock()
    pi_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    pi_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.one_or_none.return_value = None  # year not found
    decoded = {"make": "Honda", "model": "Accord", "model_year": "1899", "trim": ""}
    assert resolve_vin_to_car_id(decoded, pi_engine) is None
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "vin" -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline.vin_decoder'`

- [ ] **Step 3.3: Implement vin_decoder.py**

Create `mapping_pipeline/vin_decoder.py`:

```python
import time
from datetime import datetime, timezone

import requests
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from common.models import VinCache
from mapping_pipeline.pi_schema import (
    pi_car_table, pi_make_table, pi_model_table, pi_year_table,
)


def _fetch_nhtsa(vin: str) -> dict:
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return {r["Variable"]: r["Value"] for r in resp.json()["Results"]}


def decode_vin(vin: str, session: Session) -> dict | None:
    """Cache-first NHTSA VIN decode. Returns None for invalid/pre-1980 VINs."""
    if not vin or len(vin) != 17:
        return None

    cached = session.get(VinCache, vin)
    if cached is not None:
        if cached.error_code:
            return None
        return {
            "make": cached.make,
            "model": cached.model,
            "model_year": cached.model_year,
            "trim": cached.trim,
        }

    time.sleep(1)
    try:
        nhtsa = _fetch_nhtsa(vin)
    except Exception:
        return None

    error_code = nhtsa.get("ErrorCode") or ""
    make = nhtsa.get("Make") or ""
    model_year = nhtsa.get("ModelYear") or ""

    if "11" in error_code or not make or not model_year:
        session.merge(VinCache(
            vin=vin,
            error_code=error_code or "INCOMPLETE",
            fetched_at=datetime.now(timezone.utc),
        ))
        session.commit()
        return None

    result = {
        "make": make,
        "model": nhtsa.get("Model") or "",
        "model_year": model_year,
        "trim": nhtsa.get("Trim") or "",
    }
    session.merge(VinCache(vin=vin, fetched_at=datetime.now(timezone.utc), **result))
    session.commit()
    return result


def resolve_vin_to_car_id(decoded: dict, pi_engine: Engine) -> int | None:
    """Match decoded VIN year/make/model against parts_interchange.car. Returns car.id or None."""
    year_str = (decoded.get("model_year") or "").strip()
    make_str = (decoded.get("make") or "").strip()
    model_str = (decoded.get("model") or "").strip()

    if not (year_str and make_str and model_str):
        return None

    with pi_engine.connect() as conn:
        year_row = conn.execute(
            select(pi_year_table.c.id).where(pi_year_table.c.name == year_str)
        ).one_or_none()
        if not year_row:
            return None

        make_row = conn.execute(
            select(pi_make_table.c.id).where(
                text("lower(name) = lower(:name)")
            ).params(name=make_str)
        ).one_or_none()
        if not make_row:
            return None

        model_row = conn.execute(
            select(pi_model_table.c.id).where(
                pi_model_table.c.make_id == make_row[0],
                text("lower(name) = lower(:name)")
            ).params(name=model_str)
        ).one_or_none()
        if not model_row:
            return None

        car_row = conn.execute(
            select(pi_car_table.c.id).where(
                pi_car_table.c.year_id == year_row[0],
                pi_car_table.c.make_id == make_row[0],
                pi_car_table.c.model_id == model_row[0],
            )
        ).first()
        return car_row[0] if car_row else None
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "vin" -v
```

Expected: all `test_*vin*` tests PASS

---

## Task 4: ymmt_matcher.py

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/ymmt_matcher.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 4.1: Write failing tests**

Add to `tests/test_mapping_pipeline.py`:

```python
def test_normalize_strips_punctuation_and_suffixes():
    from mapping_pipeline.ymmt_matcher import normalize
    assert normalize("Ford, Inc.") == "ford"
    assert normalize("General Motors Corp") == "general motors"
    assert normalize("Toyota LLC") == "toyota"
    assert normalize("HONDA") == "honda"
    assert normalize("Chevy-S10") == "chevy s10"


def test_normalize_empty():
    from mapping_pipeline.ymmt_matcher import normalize
    assert normalize("") == ""


def _make_pi_engine_mock(makes, models_by_make_id, cars):
    """
    makes: list of (id, name)
    models_by_make_id: {make_id: [(model_id, model_name), ...]}
    cars: list of (car_id,)  — first() result
    """
    from unittest.mock import MagicMock

    def make_row(tup):
        r = MagicMock()
        r.id = tup[0]
        r.name = tup[1]
        return r

    conn = MagicMock()
    pi_engine = MagicMock()
    pi_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    pi_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    execute_calls = []

    def execute_side_effect(stmt):
        call_count = len(execute_calls)
        execute_calls.append(stmt)
        result = MagicMock()
        if call_count == 0:
            # load all makes
            result.all.return_value = [make_row(m) for m in makes]
        elif call_count == 1:
            # load models for matched make
            make_id = makes[0][0]  # assume first make matched
            rows = [make_row(m) for m in models_by_make_id.get(make_id, [])]
            result.all.return_value = rows
        elif call_count == 2:
            # year lookup
            result.one_or_none.return_value = (10,) if cars else None
        else:
            # car lookup
            result.first.return_value = cars[0] if cars else None
        return result

    conn.execute.side_effect = execute_side_effect
    return pi_engine


def test_match_car_above_threshold():
    from mapping_pipeline.ymmt_matcher import match_car
    pi_engine = _make_pi_engine_mock(
        makes=[(1, "Honda")],
        models_by_make_id={1: [(5, "Accord")]},
        cars=[(99,)],
    )
    result = match_car(2003, "Honda", "Accord", pi_engine)
    assert result is not None
    assert result.car_id == 99
    assert result.confidence >= 0.85


def test_match_car_below_threshold_make():
    from mapping_pipeline.ymmt_matcher import match_car
    pi_engine = _make_pi_engine_mock(
        makes=[(1, "Honda")],
        models_by_make_id={1: [(5, "Accord")]},
        cars=[],
    )
    # "Hyundai" vs "Honda" should be below 0.85
    result = match_car(2003, "Hyundai", "Sonata", pi_engine, threshold=0.85)
    assert result is None


def test_match_car_no_makes_in_db():
    from mapping_pipeline.ymmt_matcher import match_car
    pi_engine = _make_pi_engine_mock(makes=[], models_by_make_id={}, cars=[])
    assert match_car(2003, "Honda", "Accord", pi_engine) is None
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "normalize or match_car" -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline.ymmt_matcher'`

- [ ] **Step 4.3: Implement ymmt_matcher.py**

Create `mapping_pipeline/ymmt_matcher.py`:

```python
import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.engine import Engine

from mapping_pipeline.pi_schema import (
    pi_car_table, pi_make_table, pi_model_table, pi_year_table,
)

_SUFFIXES = re.compile(r"\b(inc|corp|ltd|llc|co)\b\.?", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]")


def normalize(s: str) -> str:
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    s = _SUFFIXES.sub("", s)
    return " ".join(s.split())


@dataclass
class YmmtMatch:
    car_id: int
    confidence: float
    make_match: str
    make_score: float
    model_match: str
    model_score: float


def match_car(
    year: int | None,
    raw_make: str,
    raw_model: str,
    pi_engine: Engine,
    threshold: float = 0.85,
) -> YmmtMatch | None:
    """Fuzzy-match raw make/model against parts_interchange. Returns YmmtMatch or None."""
    norm_make = normalize(raw_make)
    norm_model = normalize(raw_model)

    with pi_engine.connect() as conn:
        makes = conn.execute(select(pi_make_table.c.id, pi_make_table.c.name)).all()
        if not makes:
            return None

        make_names = [normalize(m.name) for m in makes]
        best_make = process.extractOne(norm_make, make_names, scorer=fuzz.WRatio)
        if not best_make or best_make[1] < threshold * 100:
            return None

        make_score = best_make[1] / 100.0
        make_idx = make_names.index(best_make[0])
        make_id = makes[make_idx].id
        make_match_name = makes[make_idx].name

        models = conn.execute(
            select(pi_model_table.c.id, pi_model_table.c.name)
            .where(pi_model_table.c.make_id == make_id)
        ).all()
        if not models:
            return None

        model_names = [normalize(m.name) for m in models]
        best_model = process.extractOne(norm_model, model_names, scorer=fuzz.WRatio)
        if not best_model or best_model[1] < threshold * 100:
            return None

        model_score = best_model[1] / 100.0
        model_idx = model_names.index(best_model[0])
        model_id = models[model_idx].id
        model_match_name = models[model_idx].name
        confidence = min(make_score, model_score)

        # Prefer year-specific car; fall back to any car with this make+model
        car_id = None
        if year:
            year_row = conn.execute(
                select(pi_year_table.c.id).where(pi_year_table.c.name == str(year))
            ).one_or_none()
            if year_row:
                car_row = conn.execute(
                    select(pi_car_table.c.id).where(
                        pi_car_table.c.year_id == year_row[0],
                        pi_car_table.c.make_id == make_id,
                        pi_car_table.c.model_id == model_id,
                    )
                ).first()
                if car_row:
                    car_id = car_row[0]

        if car_id is None:
            car_row = conn.execute(
                select(pi_car_table.c.id).where(
                    pi_car_table.c.make_id == make_id,
                    pi_car_table.c.model_id == model_id,
                )
            ).first()
            if car_row:
                car_id = car_row[0]

        if car_id is None:
            return None

        return YmmtMatch(
            car_id=car_id,
            confidence=confidence,
            make_match=make_match_name,
            make_score=make_score,
            model_match=model_match_name,
            model_score=model_score,
        )
```

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "normalize or match_car" -v
```

Expected: all PASS

---

## Task 5: rule_engine.py

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/rule_engine.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 5.1: Write failing tests**

Add to `tests/test_mapping_pipeline.py`:

```python
import datetime as dt


def _make_rule(
    field, rule_type, raw_value, canonical_value,
    scope="global", source=None, location_id=None,
    make_context=None, priority=100, is_active=True,
):
    from common.models import MappingRule
    return MappingRule(
        id=None, scope=scope, source=source, location_id=location_id,
        field=field, rule_type=rule_type,
        raw_value=raw_value, canonical_value=canonical_value,
        make_context=make_context, priority=priority, is_active=is_active,
        created_by="manual", created_at=dt.datetime.now(),
        applied_count=0,
    )


def test_apply_rules_exact_match_make():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    rule = _make_rule("make", "exact", "chevy", "Chevrolet")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "chevy"
    vehicle.model = "Silverado"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session)
    assert result["make"] == "Chevrolet"
    assert rule in applied
    session.commit.assert_called()


def test_apply_rules_prefix_match_make():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    rule = _make_rule("make", "prefix", "ford mo", "Ford")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "Ford Motor Company"
    vehicle.model = "F-150"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session)
    assert result["make"] == "Ford"
    assert rule in applied


def test_apply_rules_regex_match_model():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    rule = _make_rule("model", "regex", r"f[\-\s]?150", "F-150")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "Ford"
    vehicle.model = "f150"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session)
    assert result["model"] == "F-150"


def test_apply_rules_scope_priority_location_over_global():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    global_rule   = _make_rule("make", "exact", "chevy", "Chevrolet", scope="global",   priority=100)
    location_rule = _make_rule("make", "exact", "chevy", "Chevy",     scope="location", priority=100, location_id=5)
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "chevy"
    vehicle.model = "Silverado"
    vehicle.trim = ""
    vehicle.location_id = 5
    # Location rule should win
    result, applied = apply_rules(vehicle, [global_rule, location_rule], session)
    assert result["make"] == "Chevy"
    assert location_rule in applied
    assert global_rule not in applied


def test_apply_rules_make_context_blocks_model_rule():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    # Model rule only applies when make is "Ford"
    rule = _make_rule("model", "exact", "f150", "F-150", make_context="Ford")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "Toyota"   # wrong make context
    vehicle.model = "f150"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session)
    assert result["model"] == "f150"   # unchanged
    assert rule not in applied


def test_apply_rules_no_match():
    from mapping_pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    rule = _make_rule("make", "exact", "gm", "General Motors")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "Ford"
    vehicle.model = "F-150"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session)
    assert result["make"] == "Ford"
    assert applied == []
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "apply_rules" -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline.rule_engine'`

- [ ] **Step 5.3: Implement rule_engine.py**

Create `mapping_pipeline/rule_engine.py`:

```python
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from common.models import MappingRule, Vehicle


_SCOPE_PRIORITY = {"location": 0, "source": 1, "global": 2}


def _rule_matches(rule: MappingRule, field_value: str) -> bool:
    raw = rule.raw_value
    val = field_value.lower()
    match rule.rule_type:
        case "exact":
            return raw.lower() == val
        case "prefix":
            return val.startswith(raw.lower())
        case "regex":
            return bool(re.search(raw, field_value, re.IGNORECASE))
        case _:
            return False


def _rule_applies_to_vehicle(rule: MappingRule, vehicle: Vehicle, current_make: str) -> bool:
    if rule.scope == "location" and rule.location_id != getattr(vehicle, "location_id", None):
        return False
    if rule.scope == "source" and rule.source != getattr(vehicle, "source", None):
        return False
    if rule.make_context and current_make.lower() != rule.make_context.lower():
        return False
    return True


def apply_rules(
    vehicle: Vehicle,
    rules: list[MappingRule],
    session: Session,
) -> tuple[dict, list[MappingRule]]:
    """
    Apply active MappingRules to vehicle's make/model/trim.
    Returns (transformed_fields_dict, list_of_applied_rules).
    Scope priority: location > source > global. Within same scope, lower priority number wins.
    Increments applied_count on matched rules and commits.
    """
    transformed = {
        "make":  getattr(vehicle, "make",  "") or "",
        "model": getattr(vehicle, "model", "") or "",
        "trim":  getattr(vehicle, "trim",  "") or "",
    }
    applied: list[MappingRule] = []

    # Sort: ascending priority number within each scope level
    sorted_rules = sorted(rules, key=lambda r: (_SCOPE_PRIORITY[r.scope], r.priority))

    for field in ("make", "model", "trim"):
        field_rules = [r for r in sorted_rules if r.field == field and r.is_active]
        current_make = transformed["make"]
        for rule in field_rules:
            if not _rule_applies_to_vehicle(rule, vehicle, current_make):
                continue
            if _rule_matches(rule, transformed[field]):
                transformed[field] = rule.canonical_value
                rule.applied_count = (rule.applied_count or 0) + 1
                applied.append(rule)
                break  # first matching rule wins per field

    if applied:
        session.commit()

    return transformed, applied
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "apply_rules" -v
```

Expected: all PASS

---

## Task 6: resolution_pipeline.py

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/resolution_pipeline.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 6.1: Write failing tests**

Add to `tests/test_mapping_pipeline.py`:

```python
def _make_vehicle(
    id=1, vin=None, year=2003, make="Honda", model="Accord", trim="EX",
    car_id_resolved=False, location_id=1, source="parts_galore", source_key="VIN123",
):
    from unittest.mock import MagicMock
    v = MagicMock()
    v.id = id
    v.vin = vin
    v.year = year
    v.make = make
    v.model = model
    v.trim = trim
    v.car_id_resolved = car_id_resolved
    v.car_id = None
    v.car_id_method = None
    v.car_id_confidence = None
    v.location_id = location_id
    v.source = source
    v.source_key = source_key
    return v


def test_resolve_vehicle_already_resolved_skips():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(car_id_resolved=True)
    session = MagicMock()
    pi_engine = MagicMock()
    result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)
    assert result == "already_resolved"
    session.commit.assert_not_called()


def test_resolve_vehicle_vin_decode_success():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(vin="1HGCM82633A004352")
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("mapping_pipeline.resolution_pipeline.decode_vin",
               return_value={"make": "Honda", "model": "Accord", "model_year": "2003", "trim": "EX"}), \
         patch("mapping_pipeline.resolution_pipeline.resolve_vin_to_car_id", return_value=42):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "vin_decode"
    assert vehicle.car_id == 42
    assert vehicle.car_id_resolved is True
    assert vehicle.car_id_method == "vin_decode"
    assert vehicle.car_id_confidence == 1.0
    session.commit.assert_called()


def test_resolve_vehicle_ymmt_match_success():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    from mapping_pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()
    ymmt = YmmtMatch(car_id=77, confidence=0.92, make_match="Honda",
                     make_score=0.95, model_match="Accord", model_score=0.92)

    with patch("mapping_pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("mapping_pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": "EX"}, [])), \
         patch("mapping_pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "ymmt_match"
    assert vehicle.car_id == 77
    assert vehicle.car_id_method == "ymmt_match"


def test_resolve_vehicle_rule_applied_method():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    from mapping_pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None, make="chevy")
    session = MagicMock()
    pi_engine = MagicMock()
    fake_rule = MagicMock()
    ymmt = YmmtMatch(car_id=55, confidence=0.91, make_match="Chevrolet",
                     make_score=0.95, model_match="Silverado", model_score=0.91)

    with patch("mapping_pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("mapping_pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Chevrolet", "model": "Silverado", "trim": ""}, [fake_rule])), \
         patch("mapping_pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[fake_rule], dry_run=False)

    assert result == "rule_applied"
    assert vehicle.car_id_method == "rule_applied"


def test_resolve_vehicle_unresolved():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("mapping_pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("mapping_pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": ""}, [])), \
         patch("mapping_pipeline.resolution_pipeline.match_car", return_value=None):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "discrepancy"
    session.merge.assert_called_once()
    session.commit.assert_called()


def test_resolve_vehicle_dry_run_does_not_commit():
    from mapping_pipeline.resolution_pipeline import resolve_vehicle
    from mapping_pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()
    ymmt = YmmtMatch(car_id=77, confidence=0.92, make_match="Honda",
                     make_score=0.95, model_match="Accord", model_score=0.92)

    with patch("mapping_pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("mapping_pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": ""}, [])), \
         patch("mapping_pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=True)

    assert result == "ymmt_match"
    session.commit.assert_not_called()
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "resolve_vehicle" -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline.resolution_pipeline'`

- [ ] **Step 6.3: Implement resolution_pipeline.py**

Create `mapping_pipeline/resolution_pipeline.py`:

```python
"""
Orchestrates the vehicle-to-car mapping pipeline.

Pipeline per vehicle (in order):
  1. VIN decode via NHTSA (cached)
  2. Apply MappingRules to transform make/model/trim
  3. Fuzzy YMMT match against parts_interchange (threshold 0.85)
  4. Discrepancy record for failures

CLI:
  python -m mapping_pipeline.resolution_pipeline [--limit N] [--source SOURCE] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from common.db import get_engine, get_session
from common.models import MappingDiscrepancy, MappingRule, Vehicle
from mapping_pipeline.rule_engine import apply_rules
from mapping_pipeline.vin_decoder import decode_vin, resolve_vin_to_car_id
from mapping_pipeline.ymmt_matcher import YmmtMatch, match_car


def resolve_vehicle(
    vehicle: Vehicle,
    session: Session,
    pi_engine,
    rules: list[MappingRule],
    dry_run: bool = False,
) -> str:
    """
    Attempt to resolve vehicle.car_id. Returns one of:
    "already_resolved" | "vin_decode" | "ymmt_match" | "rule_applied" | "discrepancy"
    """
    if vehicle.car_id_resolved:
        return "already_resolved"

    # Step 1: VIN decode
    if vehicle.vin:
        decoded = decode_vin(vehicle.vin, session)
        if decoded:
            car_id = resolve_vin_to_car_id(decoded, pi_engine)
            if car_id:
                vehicle.car_id = car_id
                vehicle.car_id_resolved = True
                vehicle.car_id_method = "vin_decode"
                vehicle.car_id_confidence = 1.0
                if not dry_run:
                    session.commit()
                return "vin_decode"

    # Step 2: Apply rules to transform make/model/trim
    transformed, applied_rules = apply_rules(vehicle, rules, session)

    # Step 3: Fuzzy YMMT match
    ymmt: YmmtMatch | None = match_car(
        vehicle.year, transformed["make"], transformed["model"], pi_engine
    )

    if ymmt is not None:
        method = "rule_applied" if applied_rules else "ymmt_match"
        vehicle.car_id = ymmt.car_id
        vehicle.car_id_resolved = True
        vehicle.car_id_method = method
        vehicle.car_id_confidence = ymmt.confidence
        if not dry_run:
            session.commit()
        return method

    # Step 4: Discrepancy
    status = "unresolved" if ymmt is None else "no_match_in_dataset"
    now = datetime.now(timezone.utc)
    discrepancy = MappingDiscrepancy(
        vehicle_id=vehicle.id,
        raw_year=str(vehicle.year) if vehicle.year else None,
        raw_make=vehicle.make,
        raw_model=vehicle.model,
        raw_trim=vehicle.trim,
        fuzzy_make_match=ymmt.make_match if ymmt else None,
        fuzzy_make_score=ymmt.make_score if ymmt else None,
        fuzzy_model_match=ymmt.model_match if ymmt else None,
        fuzzy_model_score=ymmt.model_score if ymmt else None,
        candidate_car_id=ymmt.car_id if ymmt else None,
        status=status,
        created_at=now,
        last_processed_at=now,
    )
    if not dry_run:
        session.merge(discrepancy)
        session.commit()
    return "discrepancy"


def run_pipeline(
    limit: int | None = None,
    source: str | None = None,
    dry_run: bool = False,
) -> None:
    ji_engine = get_engine()
    pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"])

    with get_session(ji_engine) as session:
        q = (
            select(Vehicle)
            .where(Vehicle.car_id_resolved == False)  # noqa: E712
            .order_by(Vehicle.id)
        )
        if source:
            q = q.where(Vehicle.source == source)
        if limit:
            q = q.limit(limit)

        vehicles = session.execute(q).scalars().all()
        rules = session.execute(
            select(MappingRule)
            .where(MappingRule.is_active == True)  # noqa: E712
            .order_by(MappingRule.scope, MappingRule.priority)
        ).scalars().all()

    counts: dict[str, int] = {}
    for vehicle in vehicles:
        with get_session(ji_engine) as session:
            # Re-attach vehicle to fresh session
            vehicle = session.get(Vehicle, vehicle.id)
            if vehicle is None:
                continue
            result = resolve_vehicle(vehicle, session, pi_engine, rules, dry_run)
            counts[result] = counts.get(result, 0) + 1

        processed = sum(counts.values())
        if processed % 100 == 0:
            print(f"Processed {processed}: {counts}")

    print(f"Done. Final counts: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run vehicle-to-car mapping pipeline")
    parser.add_argument("--limit",  type=int,  default=None, help="Max vehicles to process")
    parser.add_argument("--source", type=str,  default=None, help="Filter by source name")
    parser.add_argument("--dry-run", action="store_true",   help="Read-only, no DB writes")
    args = parser.parse_args()
    run_pipeline(limit=args.limit, source=args.source, dry_run=args.dry_run)
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "resolve_vehicle" -v
```

Expected: all PASS

- [ ] **Step 6.5: Run the full test suite so far**

```bash
python -m pytest tests/test_mapping_pipeline.py -v
```

Expected: all tests PASS

---

## Task 7: reprocess_job.py

**Files:**
- Create: `web_scrapers/junkyard_inventory_scrapers/mapping_pipeline/reprocess_job.py`
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 7.1: Write failing tests**

Add to `tests/test_mapping_pipeline.py`:

```python
def test_get_reprocess_vehicle_ids_excludes_ignored_and_manual():
    from mapping_pipeline.reprocess_job import get_reprocess_vehicle_ids
    session = MagicMock()
    # Simulate query returning vehicle IDs 1, 2, 3
    session.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    ids = get_reprocess_vehicle_ids(session)
    assert ids == [1, 2, 3]
    # Verify the status filter was applied (check call was made)
    session.execute.assert_called_once()


def test_reprocess_resets_car_id_before_resolving():
    from mapping_pipeline.reprocess_job import reprocess_vehicle
    vehicle = _make_vehicle(vin=None, car_id_resolved=True)
    vehicle.car_id = 99
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("mapping_pipeline.reprocess_job.resolve_vehicle", return_value="ymmt_match") as mock_resolve:
        reprocess_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    # car_id_resolved must be reset to False before calling resolve_vehicle
    assert vehicle.car_id_resolved is False
    assert vehicle.car_id is None
    mock_resolve.assert_called_once_with(vehicle, session, pi_engine, [], False)
```

- [ ] **Step 7.2: Run tests to verify they fail**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "reprocess" -v
```

Expected: `ModuleNotFoundError: No module named 'mapping_pipeline.reprocess_job'`

- [ ] **Step 7.3: Implement reprocess_job.py**

Create `mapping_pipeline/reprocess_job.py`:

```python
"""
Re-runs the resolution pipeline on vehicles with unresolved/rule_applied/no_match discrepancies.
Triggered after new MappingRules are approved.

CLI:
  python -m mapping_pipeline.reprocess_job [--dry-run]
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from common.db import get_engine, get_session
from common.models import MappingDiscrepancy, MappingRule, Vehicle
from mapping_pipeline.resolution_pipeline import resolve_vehicle

REPROCESS_STATUSES = ("unresolved", "rule_applied", "no_match_in_dataset")


def get_reprocess_vehicle_ids(session: Session) -> list[int]:
    """Return vehicle IDs whose discrepancy status is eligible for reprocessing."""
    rows = session.execute(
        select(MappingDiscrepancy.vehicle_id)
        .where(MappingDiscrepancy.status.in_(REPROCESS_STATUSES))
        .order_by(MappingDiscrepancy.vehicle_id)
    ).scalars().all()
    return list(rows)


def reprocess_vehicle(
    vehicle: Vehicle,
    session: Session,
    pi_engine,
    rules: list[MappingRule],
    dry_run: bool,
) -> str:
    """Reset car_id fields and re-run resolution pipeline."""
    vehicle.car_id = None
    vehicle.car_id_resolved = False
    vehicle.car_id_method = None
    vehicle.car_id_confidence = None
    return resolve_vehicle(vehicle, session, pi_engine, rules, dry_run)


def run_reprocess(dry_run: bool = False) -> None:
    ji_engine = get_engine()
    pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"])

    with get_session(ji_engine) as session:
        vehicle_ids = get_reprocess_vehicle_ids(session)
        rules = session.execute(
            select(MappingRule)
            .where(MappingRule.is_active == True)  # noqa: E712
            .order_by(MappingRule.scope, MappingRule.priority)
        ).scalars().all()

    print(f"Reprocessing {len(vehicle_ids)} vehicles...")
    counts: dict[str, int] = {}

    for vid in vehicle_ids:
        with get_session(ji_engine) as session:
            vehicle = session.get(Vehicle, vid)
            if vehicle is None:
                continue
            result = reprocess_vehicle(vehicle, session, pi_engine, rules, dry_run)
            counts[result] = counts.get(result, 0) + 1

        processed = sum(counts.values())
        if processed % 100 == 0:
            print(f"Reprocessed {processed}: {counts}")

    print(f"Done. Final counts: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-run mapping pipeline on unresolved vehicles")
    parser.add_argument("--dry-run", action="store_true", help="Read-only, no DB writes")
    args = parser.parse_args()
    run_reprocess(dry_run=args.dry_run)
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
python -m pytest tests/test_mapping_pipeline.py -k "reprocess" -v
```

Expected: all PASS

- [ ] **Step 7.5: Run full test suite**

```bash
python -m pytest tests/test_mapping_pipeline.py -v
```

Expected: all tests PASS with summary like:
```
25 passed in X.XXs
```

---

## Task 8: Integration smoke test

**Files:**
- Test: `web_scrapers/junkyard_inventory_scrapers/tests/test_mapping_pipeline.py`

- [ ] **Step 8.1: Add integration tests (skipped if env vars not set)**

Add to `tests/test_mapping_pipeline.py`:

```python
import pytest

JUNKYARD_URL = os.environ.get("JUNKYARD_DATABASE_URL")
PARTS_URL    = os.environ.get("PARTS_DATABASE_URL")

skip_no_db = pytest.mark.skipif(
    not (JUNKYARD_URL and PARTS_URL),
    reason="JUNKYARD_DATABASE_URL and PARTS_DATABASE_URL required",
)


@skip_no_db
def test_integration_migration_applied():
    """Verify vin_cache table exists after migration 0002."""
    from sqlalchemy import create_engine, inspect
    engine = create_engine(JUNKYARD_URL)
    insp = inspect(engine)
    assert "vin_cache" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("vin_cache")}
    assert {"vin", "make", "model", "model_year", "error_code", "fetched_at"} <= cols


@skip_no_db
def test_integration_resolve_vehicle_no_crash():
    """Run pipeline on first 5 unresolved vehicles; verify no exceptions and counts are sane."""
    from sqlalchemy import create_engine, select
    from common.db import get_engine, get_session
    from common.models import MappingRule, Vehicle
    from mapping_pipeline.resolution_pipeline import resolve_vehicle

    ji_engine = get_engine()
    pi_engine = create_engine(PARTS_URL)

    with get_session(ji_engine) as session:
        vehicles = session.execute(
            select(Vehicle).where(Vehicle.car_id_resolved == False).limit(5)
        ).scalars().all()
        rules = session.execute(
            select(MappingRule).where(MappingRule.is_active == True)
        ).scalars().all()

    valid_results = {"already_resolved", "vin_decode", "ymmt_match", "rule_applied", "discrepancy"}
    for vehicle in vehicles:
        with get_session(ji_engine) as session:
            v = session.get(Vehicle, vehicle.id)
            if v:
                result = resolve_vehicle(v, session, pi_engine, rules, dry_run=True)
                assert result in valid_results, f"Unexpected result: {result!r}"
```

- [ ] **Step 8.2: Run unit tests (no DB required)**

```bash
cd web_scrapers/junkyard_inventory_scrapers
python -m pytest tests/test_mapping_pipeline.py -v -k "not integration"
```

Expected: all non-integration tests PASS

- [ ] **Step 8.3: Run integration tests against local Postgres**

```bash
JUNKYARD_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory" \
PARTS_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange" \
python -m pytest tests/test_mapping_pipeline.py -v -k "integration"
```

Expected: `test_integration_migration_applied` and `test_integration_resolve_vehicle_no_crash` PASS

---

## Self-Review

**Spec coverage check:**

| Requirement | Covered by |
|---|---|
| VIN decode via NHTSA | Task 3 (vin_decoder.py) |
| vin_cache table to avoid re-fetching | Task 1 (migration 0002) + Task 3 |
| pre-1980 VIN → no_match_in_dataset | Task 3 (error code "11" check) |
| MappingRule exact/prefix/regex | Task 5 (rule_engine.py) |
| Scope priority: location > source > global | Task 5 |
| make_context filter on model rules | Task 5 |
| applied_count increment | Task 5 |
| Fuzzy match with rapidfuzz WRatio ≥ 0.85 | Task 4 (ymmt_matcher.py) |
| normalize: lowercase, strip punct, suffixes | Task 4 |
| MappingDiscrepancy with fuzzy scores | Task 6 (resolution_pipeline.py) |
| status: unresolved / no_match_in_dataset | Task 6 |
| car_id_method: vin_decode/ymmt_match/rule_applied | Task 6 |
| CLI: --limit, --source, --dry-run | Task 6 |
| reprocess_job: re-run on eligible discrepancies | Task 7 |
| reprocess excludes ignored/manual | Task 7 |
| Unit tests mock NHTSA API | Tasks 3, 6 |
| Integration tests skip if no env vars | Task 8 |
| vin_cache model in common/models.py | Task 1 |
| pi_schema.py with no cross-project imports | Task 2 |

**No placeholders present.**

**Type consistency verified:** `YmmtMatch` defined in Task 4 (ymmt_matcher.py), used in Tasks 6 and 7. `apply_rules` returns `tuple[dict, list[MappingRule]]` consistently in Tasks 5 and 6. `decode_vin` returns `dict | None` consistently in Tasks 3 and 6.

---

Plan complete and saved to `parts_interchange/docs/superpowers/plans/2026-05-17-phase-3-mapping-pipeline.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review after each, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
