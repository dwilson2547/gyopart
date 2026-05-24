# Phase 0: Database Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `junkyard_inventory` and `parts_interchange` databases to the existing scrape_stack PostgreSQL cluster, apply the canonical junkyard schema via Alembic, and apply the parts-interchange schema via parts-loader-v2 — all verified with integration smoke tests.

**Architecture:** The scrape_stack already runs a Postgres 16 container (host port 5433, container port 5432, user `scrapestack`). It uses an initdb SQL script to create databases on first start; we extend that script and also apply the changes to the already-running container. The junkyard_inventory schema is managed by Alembic sitting at the root of `junkyard_inventory_scrapers/`. The parts_interchange schema is applied by parts-loader-v2's existing `--init-schema` flag pointed at the same cluster.

**Tech Stack:** PostgreSQL 16 (Docker), Alembic 1.13+, SQLAlchemy 2.x, psycopg2-binary, pytest, Python 3.11+

---

## Files

**Modify:**

- `web_scrapers/scrape_stack/initdb/01-create-databases.sql` — add `junkyard_inventory` and `parts_interchange`
- `web_scrapers/junkyard_inventory_scrapers/common/models.py` — rewrite to canonical schema (flatten VehicleDetail, add extras, car_id fields, MappingRule, MappingDiscrepancy)
- `parts_interchange/parts-loader-v2/src/config.py` — change default port to 5433 and user to scrapestack

**Create:**

- `web_scrapers/junkyard_inventory_scrapers/requirements-migration.txt` — alembic + psycopg2 + sqlalchemy
- `web_scrapers/junkyard_inventory_scrapers/alembic.ini` — alembic config pointing at env var for URL
- `web_scrapers/junkyard_inventory_scrapers/alembic/env.py` — wires SQLAlchemy Base to alembic
- `web_scrapers/junkyard_inventory_scrapers/alembic/script.py.mako` — standard migration template
- `web_scrapers/junkyard_inventory_scrapers/alembic/versions/0001_initial_junkyard_schema.py` — creates all junkyard_inventory tables
- `web_scrapers/junkyard_inventory_scrapers/tests/__init__.py` — empty
- `web_scrapers/junkyard_inventory_scrapers/tests/test_db_foundation.py` — integration smoke tests for both databases

---

## Task 1: Add databases to scrape_stack and verify connectivity

**Files:**

- Modify: `web_scrapers/scrape_stack/initdb/01-create-databases.sql`
- Create: `web_scrapers/junkyard_inventory_scrapers/tests/__init__.py`
- Create: `web_scrapers/junkyard_inventory_scrapers/tests/test_db_foundation.py`

- [ ] **Step 1: Write the failing connectivity tests**

Create `web_scrapers/junkyard_inventory_scrapers/tests/__init__.py` (empty file).

Create `web_scrapers/junkyard_inventory_scrapers/tests/test_db_foundation.py`:

```python
"""
Integration smoke tests for Phase 0 database foundation.

Requires:
  JUNKYARD_DATABASE_URL=postgresql://scrapestack:<pass>@localhost:5433/junkyard_inventory
  PARTS_DATABASE_URL=postgresql://scrapestack:<pass>@localhost:5433/parts_interchange

Run from web_scrapers/junkyard_inventory_scrapers/:
  JUNKYARD_DATABASE_URL=... PARTS_DATABASE_URL=... pytest tests/test_db_foundation.py -v
"""

import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _make_engine(url: str):
    return create_engine(url, pool_pre_ping=True)


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables"
            "  WHERE table_schema='public' AND table_name=:name"
            ")"
        ),
        {"name": table_name},
    )
    return row.scalar()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.columns"
            "  WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ")"
        ),
        {"t": table_name, "c": column_name},
    )
    return row.scalar()


# ── Junkyard fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def junkyard_engine():
    url = os.environ.get(
        "JUNKYARD_DATABASE_URL",
        "postgresql://scrapestack:@localhost:5433/junkyard_inventory",
    )
    engine = _make_engine(url)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"junkyard_inventory DB not reachable: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def jconn(junkyard_engine):
    with junkyard_engine.connect() as conn:
        yield conn


# ── Parts fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def parts_engine():
    url = os.environ.get(
        "PARTS_DATABASE_URL",
        "postgresql://scrapestack:@localhost:5433/parts_interchange",
    )
    engine = _make_engine(url)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"parts_interchange DB not reachable: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def pconn(parts_engine):
    with parts_engine.connect() as conn:
        yield conn


# ── Connectivity tests (Task 1) ──────────────────────────────────────────────

def test_junkyard_db_is_reachable(jconn):
    result = jconn.execute(text("SELECT 1"))
    assert result.scalar() == 1


def test_parts_db_is_reachable(pconn):
    result = pconn.execute(text("SELECT 1"))
    assert result.scalar() == 1


# ── Junkyard schema tests (Task 4) ──────────────────────────────────────────

def test_locations_table_exists(jconn):
    assert _table_exists(jconn, "locations")


def test_vehicles_table_exists(jconn):
    assert _table_exists(jconn, "vehicles")


def test_mapping_rules_table_exists(jconn):
    assert _table_exists(jconn, "mapping_rules")


def test_mapping_discrepancies_table_exists(jconn):
    assert _table_exists(jconn, "mapping_discrepancies")


def test_scrape_runs_table_exists(jconn):
    assert _table_exists(jconn, "scrape_runs")


def test_vehicle_details_table_does_not_exist(jconn):
    assert not _table_exists(jconn, "vehicle_details")


def test_vehicles_has_car_id_columns(jconn):
    for col in ("car_id", "car_id_resolved", "car_id_method", "car_id_confidence"):
        assert _column_exists(jconn, "vehicles", col), f"Missing column: vehicles.{col}"


def test_vehicles_has_extras_column(jconn):
    assert _column_exists(jconn, "vehicles", "extras")


def test_vehicles_has_flattened_detail_columns(jconn):
    flat_cols = [
        "trim", "vehicle_type", "body_type", "body_sub_type", "doors", "style",
        "drive_type", "fuel_type", "engine_block", "engine_cylinders",
        "engine_size", "engine_aspiration", "trans_type", "trans_speeds",
        "mileage", "preview_image_url", "detail_fetched_at",
    ]
    for col in flat_cols:
        assert _column_exists(jconn, "vehicles", col), f"Missing column: vehicles.{col}"


# ── Parts schema tests (Task 5) ──────────────────────────────────────────────

def test_car_table_exists(pconn):
    assert _table_exists(pconn, "car")


def test_part_table_exists(pconn):
    assert _table_exists(pconn, "part")


def test_car_parts_table_exists(pconn):
    assert _table_exists(pconn, "car_parts")


def test_make_table_exists(pconn):
    assert _table_exists(pconn, "make")


def test_model_table_exists(pconn):
    assert _table_exists(pconn, "model")
```

- [ ] **Step 2: Run the tests to confirm they fail (cannot connect)**

Run from `web_scrapers/junkyard_inventory_scrapers/`:

```bash
cd web_scrapers/junkyard_inventory_scrapers
pip install sqlalchemy psycopg2-binary pytest
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py::test_junkyard_db_is_reachable \
       tests/test_db_foundation.py::test_parts_db_is_reachable -v
```

Expected: both tests skip with "DB not reachable" (databases don't exist yet).

- [ ] **Step 3: Update the initdb SQL to add both databases**

Edit `web_scrapers/scrape_stack/initdb/01-create-databases.sql`:

```sql
-- Creates one database per service.
-- Runs automatically on first Postgres container start via /docker-entrypoint-initdb.d.
CREATE DATABASE webcache;
CREATE DATABASE imgcache;
CREATE DATABASE filecache;
CREATE DATABASE vidcache;
CREATE DATABASE request_auth;
CREATE DATABASE junkyard_inventory;
CREATE DATABASE parts_interchange;
```

- [ ] **Step 4: Apply the new databases to the already-running container**

The initdb script only runs on the very first container start (when the data directory is empty). Since the container is already running with data, CREATE DATABASE manually:

```bash
docker exec -i scrape_stack-postgres-1 \
  psql -U scrapestack -c "CREATE DATABASE junkyard_inventory;" postgres
docker exec -i scrape_stack-postgres-1 \
  psql -U scrapestack -c "CREATE DATABASE parts_interchange;" postgres
```

Expected output for each:

```
CREATE DATABASE
```

If the container name differs, find it with: `docker ps --filter name=postgres --format '{{.Names}}'`

- [ ] **Step 5: Run the connectivity tests again — they should pass**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py::test_junkyard_db_is_reachable \
       tests/test_db_foundation.py::test_parts_db_is_reachable -v
```

Expected: PASSED, PASSED.

- [ ] **Step 6: Commit**

```bash
cd web_scrapers
git add scrape_stack/initdb/01-create-databases.sql \
        junkyard_inventory_scrapers/tests/__init__.py \
        junkyard_inventory_scrapers/tests/test_db_foundation.py
git commit -m "feat: add junkyard_inventory and parts_interchange databases to scrape_stack"
```

---

## Task 2: Rewrite common/models.py to canonical schema

**Files:**

- Modify: `web_scrapers/junkyard_inventory_scrapers/common/models.py`

- [ ] **Step 1: Run the model structure test to confirm it fails**

```bash
cd web_scrapers/junkyard_inventory_scrapers
python -c "
from common.models import Vehicle, MappingRule, MappingDiscrepancy
# These attributes don't exist yet
assert hasattr(Vehicle, 'extras'), 'extras missing'
assert hasattr(Vehicle, 'car_id'), 'car_id missing'
assert hasattr(Vehicle, 'engine_cylinders'), 'engine_cylinders missing'
assert hasattr(MappingRule, '__tablename__'), 'MappingRule not a model'
assert hasattr(MappingDiscrepancy, '__tablename__'), 'MappingDiscrepancy not a model'
print('OK')
"
```

Expected: `ImportError: cannot import name 'MappingRule'` (or similar — the new classes don't exist yet).

- [ ] **Step 2: Rewrite common/models.py**

Replace the entire contents of `web_scrapers/junkyard_inventory_scrapers/common/models.py`:

```python
"""
Common SQLAlchemy models shared across all junkyard inventory scrapers.
Every scraper writes into these tables using the common db session.
VehicleDetail has been eliminated — all fields are flat on Vehicle.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("source", "source_location_id", name="uq_location_source"),
    )

    id                 = Column(Integer,     primary_key=True, autoincrement=True)
    source             = Column(String(100), nullable=False, index=True)
    source_location_id = Column(String(100), nullable=False)
    name               = Column(String(200), nullable=False)
    chain              = Column(String(100), nullable=True)
    address            = Column(String(500), nullable=True)
    city               = Column(String(100), nullable=True)
    state              = Column(String(10),  nullable=True)
    zip_code           = Column(String(20),  nullable=True)
    phone              = Column(String(50),  nullable=True)
    lat                = Column(Float,       nullable=True)
    lng                = Column(Float,       nullable=True)
    is_active          = Column(Boolean,     nullable=False, default=True)
    first_seen_at      = Column(DateTime,    nullable=False)
    last_seen_at       = Column(DateTime,    nullable=False)

    vehicles    = relationship("Vehicle",   back_populates="location")
    scrape_runs = relationship("ScrapeRun", back_populates="location")

    def __repr__(self) -> str:
        return f"<Location {self.source!r} {self.name!r}>"


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("source", "source_key", name="uq_vehicle_source"),
    )

    id          = Column(Integer,     primary_key=True, autoincrement=True)
    location_id = Column(Integer,     ForeignKey("locations.id"), nullable=False, index=True)
    source      = Column(String(100), nullable=False, index=True)
    source_key  = Column(String(200), nullable=False)

    # Core identity
    year         = Column(Integer,     nullable=True)
    make         = Column(String(100), nullable=True)
    model        = Column(String(200), nullable=True)
    vin          = Column(String(17),  nullable=True, index=True)
    row          = Column(String(20),  nullable=True)
    arrival_date = Column(DateTime,    nullable=True)
    color        = Column(String(100), nullable=True)

    # Formerly VehicleDetail — flattened in
    trim              = Column(String(200), nullable=True)
    vehicle_type      = Column(String(100), nullable=True)   # Car/Truck/SUV
    body_type         = Column(String(100), nullable=True)
    body_sub_type     = Column(String(100), nullable=True)
    doors             = Column(Integer,     nullable=True)
    style             = Column(String(200), nullable=True)
    drive_type        = Column(String(50),  nullable=True)   # FWD/RWD/AWD/4WD
    fuel_type         = Column(String(50),  nullable=True)   # G/D/E/H
    engine_block      = Column(String(10),  nullable=True)   # I/V/H
    engine_cylinders  = Column(Integer,     nullable=True)
    engine_size       = Column(Float,       nullable=True)    # litres
    engine_aspiration = Column(String(50),  nullable=True)   # N/A or T
    trans_type        = Column(String(10),  nullable=True)   # A/M/CVT
    trans_speeds      = Column(Integer,     nullable=True)
    mileage           = Column(Integer,     nullable=True)
    preview_image_url = Column(String(500), nullable=True)
    detail_fetched_at = Column(DateTime,    nullable=True)
    extras            = Column(JSONB,       nullable=True)    # yard-specific overflow

    # Car-ID mapping — populated by resolution pipeline (Phase 3)
    car_id            = Column(Integer,    nullable=True, index=True)
    car_id_resolved   = Column(Boolean,    nullable=False, default=False)
    car_id_method     = Column(String(20), nullable=True)    # vin_decode|ymmt_match|manual|rule_applied
    car_id_confidence = Column(Float,      nullable=True)

    # Bookkeeping
    is_active     = Column(Boolean,  nullable=False, default=True)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at  = Column(DateTime, nullable=False)

    location = relationship("Location", back_populates="vehicles")

    def __repr__(self) -> str:
        return f"<Vehicle {self.year} {self.make} {self.model} @ {self.source!r}>"


class MappingRule(Base):
    __tablename__ = "mapping_rules"

    id              = Column(Integer,      primary_key=True, autoincrement=True)
    scope           = Column(String(20),   nullable=False)    # global|source|location
    source          = Column(String(100),  nullable=True)
    location_id     = Column(Integer,      ForeignKey("locations.id"), nullable=True)
    field           = Column(String(50),   nullable=False)    # make|model|trim
    rule_type       = Column(String(20),   nullable=False)    # exact|prefix|regex
    raw_value       = Column(String(200),  nullable=False)
    canonical_value = Column(String(200),  nullable=False)
    make_context    = Column(String(100),  nullable=True)
    priority        = Column(Integer,      nullable=False, default=100)
    is_active       = Column(Boolean,      nullable=False, default=True)
    created_by      = Column(String(20),   nullable=False)    # manual|llm_suggested|import
    created_at      = Column(DateTime,     nullable=False)
    applied_count   = Column(Integer,      nullable=False, default=0)
    llm_confidence  = Column(Float,        nullable=True)
    llm_rationale   = Column(String(1000), nullable=True)
    approved_at     = Column(DateTime,     nullable=True)
    approved_by     = Column(String(100),  nullable=True)


class MappingDiscrepancy(Base):
    __tablename__ = "mapping_discrepancies"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_discrepancy_vehicle"),
    )

    id         = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"),      nullable=False)
    raw_year   = Column(String(20),  nullable=True)
    raw_make   = Column(String(100), nullable=True)
    raw_model  = Column(String(200), nullable=True)
    raw_trim   = Column(String(200), nullable=True)

    fuzzy_make_match  = Column(String(100), nullable=True)
    fuzzy_make_score  = Column(Float,       nullable=True)
    fuzzy_model_match = Column(String(200), nullable=True)
    fuzzy_model_score = Column(Float,       nullable=True)
    candidate_car_id  = Column(Integer,     nullable=True)

    # unresolved | pending_rule | rule_applied | manual | ignored | no_match_in_dataset
    status = Column(String(30), nullable=False, default="unresolved")

    resolved_car_id     = Column(Integer,  nullable=True)
    resolved_by_rule_id = Column(Integer,  ForeignKey("mapping_rules.id"), nullable=True)
    resolved_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, nullable=False)
    last_processed_at   = Column(DateTime, nullable=True)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id            = Column(Integer,      primary_key=True, autoincrement=True)
    source        = Column(String(100),  nullable=False, index=True)
    location_id   = Column(Integer,      ForeignKey("locations.id"), nullable=True)
    started_at    = Column(DateTime,     nullable=False)
    completed_at  = Column(DateTime,     nullable=True)
    total_in_feed = Column(Integer,      nullable=True)
    new_vehicles     = Column(Integer,   nullable=False, default=0)
    updated_vehicles = Column(Integer,   nullable=False, default=0)
    removed_vehicles = Column(Integer,   nullable=False, default=0)
    success       = Column(Boolean,      nullable=False, default=False)
    error_message = Column(String(1000), nullable=True)

    location = relationship("Location", back_populates="scrape_runs")
```

- [ ] **Step 3: Run the model structure test — it should pass**

```bash
cd web_scrapers/junkyard_inventory_scrapers
python -c "
from common.models import Vehicle, MappingRule, MappingDiscrepancy, ScrapeRun, Location
assert hasattr(Vehicle, 'extras'), 'extras missing'
assert hasattr(Vehicle, 'car_id'), 'car_id missing'
assert hasattr(Vehicle, 'engine_cylinders'), 'engine_cylinders missing'
assert hasattr(Vehicle, 'trim'), 'trim missing'
assert hasattr(Vehicle, 'drive_type'), 'drive_type missing'
assert MappingRule.__tablename__ == 'mapping_rules'
assert MappingDiscrepancy.__tablename__ == 'mapping_discrepancies'
# Confirm VehicleDetail is gone
try:
    from common.models import VehicleDetail
    raise AssertionError('VehicleDetail should not exist')
except ImportError:
    pass
print('All model structure checks passed')
"
```

Expected: `All model structure checks passed`

- [ ] **Step 4: Commit**

```bash
cd web_scrapers
git add junkyard_inventory_scrapers/common/models.py
git commit -m "feat: rewrite common models to canonical schema (flatten VehicleDetail, add car_id + extras)"
```

---

## Task 3: Set up Alembic project for junkyard_inventory

**Files:**

- Create: `web_scrapers/junkyard_inventory_scrapers/requirements-migration.txt`
- Create: `web_scrapers/junkyard_inventory_scrapers/alembic.ini`
- Create: `web_scrapers/junkyard_inventory_scrapers/alembic/env.py`
- Create: `web_scrapers/junkyard_inventory_scrapers/alembic/script.py.mako`

- [ ] **Step 1: Create requirements-migration.txt**

Create `web_scrapers/junkyard_inventory_scrapers/requirements-migration.txt`:

```
alembic>=1.13
psycopg2-binary>=2.9
sqlalchemy>=2.0
```

- [ ] **Step 2: Install migration dependencies**

```bash
cd web_scrapers/junkyard_inventory_scrapers
pip install -r requirements-migration.txt
```

Expected: packages install without errors.

- [ ] **Step 3: Create alembic.ini**

Create `web_scrapers/junkyard_inventory_scrapers/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Note: `sqlalchemy.url` is intentionally absent — env.py reads `JUNKYARD_DATABASE_URL` at runtime.

- [ ] **Step 4: Create alembic/env.py**

Create `web_scrapers/junkyard_inventory_scrapers/alembic/env.py`:

```python
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ.get("JUNKYARD_DATABASE_URL")
    if not url:
        raise RuntimeError("JUNKYARD_DATABASE_URL environment variable is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Create alembic/script.py.mako**

Create `web_scrapers/junkyard_inventory_scrapers/alembic/script.py.mako`:

```
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Verify alembic can read the project**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
alembic current
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

No revision printed — the database exists but no migrations have run yet. That's correct.

- [ ] **Step 7: Commit**

```bash
cd web_scrapers
git add junkyard_inventory_scrapers/requirements-migration.txt \
        junkyard_inventory_scrapers/alembic.ini \
        junkyard_inventory_scrapers/alembic/env.py \
        junkyard_inventory_scrapers/alembic/script.py.mako
git commit -m "feat: set up Alembic project for junkyard_inventory schema management"
```

---

## Task 4: Write and apply the initial junkyard_inventory migration

**Files:**

- Create: `web_scrapers/junkyard_inventory_scrapers/alembic/versions/0001_initial_junkyard_schema.py`

- [ ] **Step 1: Run the schema tests to confirm they fail (tables don't exist yet)**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py -k "junkyard" -v
```

Expected: tests skipping or failing with "relation does not exist" style errors on the schema-checking tests. The connectivity test (`test_junkyard_db_is_reachable`) should PASS; the table-existence tests should FAIL.

- [ ] **Step 2: Create the migration file**

Create `web_scrapers/junkyard_inventory_scrapers/alembic/versions/0001_initial_junkyard_schema.py`:

```python
"""Initial junkyard_inventory schema

Revision ID: 0001
Revises:
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_location_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("chain", sa.String(100), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(10), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_location_id", name="uq_location_source"),
    )
    op.create_index("ix_locations_source", "locations", ["source"])

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_key", sa.String(200), nullable=False),
        # Core identity
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("vin", sa.String(17), nullable=True),
        sa.Column("row", sa.String(20), nullable=True),
        sa.Column("arrival_date", sa.DateTime(), nullable=True),
        sa.Column("color", sa.String(100), nullable=True),
        # Flattened from VehicleDetail
        sa.Column("trim", sa.String(200), nullable=True),
        sa.Column("vehicle_type", sa.String(100), nullable=True),
        sa.Column("body_type", sa.String(100), nullable=True),
        sa.Column("body_sub_type", sa.String(100), nullable=True),
        sa.Column("doors", sa.Integer(), nullable=True),
        sa.Column("style", sa.String(200), nullable=True),
        sa.Column("drive_type", sa.String(50), nullable=True),
        sa.Column("fuel_type", sa.String(50), nullable=True),
        sa.Column("engine_block", sa.String(10), nullable=True),
        sa.Column("engine_cylinders", sa.Integer(), nullable=True),
        sa.Column("engine_size", sa.Float(), nullable=True),
        sa.Column("engine_aspiration", sa.String(50), nullable=True),
        sa.Column("trans_type", sa.String(10), nullable=True),
        sa.Column("trans_speeds", sa.Integer(), nullable=True),
        sa.Column("mileage", sa.Integer(), nullable=True),
        sa.Column("preview_image_url", sa.String(500), nullable=True),
        sa.Column("detail_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("extras", JSONB(), nullable=True),
        # Car-ID mapping
        sa.Column("car_id", sa.Integer(), nullable=True),
        sa.Column("car_id_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("car_id_method", sa.String(20), nullable=True),
        sa.Column("car_id_confidence", sa.Float(), nullable=True),
        # Bookkeeping
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_key", name="uq_vehicle_source"),
    )
    op.create_index("ix_vehicles_location_id", "vehicles", ["location_id"])
    op.create_index("ix_vehicles_source", "vehicles", ["source"])
    op.create_index("ix_vehicles_vin", "vehicles", ["vin"])
    op.create_index("ix_vehicles_car_id", "vehicles", ["car_id"])

    op.create_table(
        "mapping_rules",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("raw_value", sa.String(200), nullable=False),
        sa.Column("canonical_value", sa.String(200), nullable=False),
        sa.Column("make_context", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("llm_rationale", sa.String(1000), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_in_feed", sa.Integer(), nullable=True),
        sa.Column("new_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_vehicles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])

    op.create_table(
        "mapping_discrepancies",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("raw_year", sa.String(20), nullable=True),
        sa.Column("raw_make", sa.String(100), nullable=True),
        sa.Column("raw_model", sa.String(200), nullable=True),
        sa.Column("raw_trim", sa.String(200), nullable=True),
        sa.Column("fuzzy_make_match", sa.String(100), nullable=True),
        sa.Column("fuzzy_make_score", sa.Float(), nullable=True),
        sa.Column("fuzzy_model_match", sa.String(200), nullable=True),
        sa.Column("fuzzy_model_score", sa.Float(), nullable=True),
        sa.Column("candidate_car_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="unresolved"),
        sa.Column("resolved_car_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by_rule_id", sa.Integer(), sa.ForeignKey("mapping_rules.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_discrepancy_vehicle"),
    )


def downgrade() -> None:
    op.drop_table("mapping_discrepancies")
    op.drop_index("ix_scrape_runs_source", table_name="scrape_runs")
    op.drop_table("scrape_runs")
    op.drop_table("mapping_rules")
    op.drop_index("ix_vehicles_car_id", table_name="vehicles")
    op.drop_index("ix_vehicles_vin", table_name="vehicles")
    op.drop_index("ix_vehicles_source", table_name="vehicles")
    op.drop_index("ix_vehicles_location_id", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("ix_locations_source", table_name="locations")
    op.drop_table("locations")
```

- [ ] **Step 3: Apply the migration**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
alembic upgrade head
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Initial junkyard_inventory schema
```

- [ ] **Step 4: Verify the migration is recorded**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
alembic current
```

Expected output:

```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0001 (head)
```

- [ ] **Step 5: Run the junkyard schema tests — they should all pass**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py -k "junkyard or vehicle or location or mapping or scrape_runs or detail_table" -v
```

Expected: all junkyard-related tests PASS.

- [ ] **Step 6: Commit**

```bash
cd web_scrapers
git add junkyard_inventory_scrapers/alembic/versions/0001_initial_junkyard_schema.py
git commit -m "feat: add initial Alembic migration for junkyard_inventory schema"
```

---

## Task 5: Apply the parts_interchange schema

**Files:**

- Modify: `parts_interchange/parts-loader-v2/src/config.py`

The parts-loader-v2 currently defaults to `localhost:5432` with `parts_user`. We're moving to the scrape_stack Postgres at `localhost:5433` with the `scrapestack` user. Update the defaults so the loader works out-of-the-box without env vars when run from a dev machine with scrape_stack running.

- [ ] **Step 1: Run the parts schema tests — they should fail (schema not applied yet)**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py -k "parts or car or make or model" -v
```

Expected: FAIL — `test_car_table_exists` etc. fail because the schema hasn't been applied to `parts_interchange` yet.

- [ ] **Step 2: Update parts-loader-v2/src/config.py defaults**

Edit `parts_interchange/parts-loader-v2/src/config.py`:

```python
import os
from urllib.parse import quote_plus


def get_psycopg2_params() -> dict:
    return {
        'user':   os.getenv('db_user', 'scrapestack'),
        'password': os.getenv('db_pass', ''),
        'host':   os.getenv('db_host', 'localhost'),
        'port':   int(os.getenv('db_port', '5433')),
        'dbname': os.getenv('db_name', 'parts_interchange'),
    }


def get_db_url() -> str:
    p = get_psycopg2_params()
    return (
        f"postgresql://{p['user']}:{quote_plus(p['password'])}"
        f"@{p['host']}:{p['port']}/{p['dbname']}"
    )
```

The `db_pass` default is intentionally empty string — callers must set `db_pass` (or `POSTGRES_PASSWORD`) because scrape_stack requires a password. The loader will fail with a clear auth error if it's not set, rather than failing with a confusing host-not-found error.

- [ ] **Step 3: Apply the parts_interchange schema**

```bash
cd parts_interchange/parts-loader-v2
mkdir -p /tmp/empty_csvs
db_pass=${POSTGRES_PASSWORD} python src/load_csvs.py --init-schema --csv-dir /tmp/empty_csvs
```

Expected output:

```
Creating schema from .../schema.sql ...
Schema ready.

No per-make CSV subdirectories found — nothing to load.
```

- [ ] **Step 4: Run the parts schema tests — they should pass**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py -k "parts or car or make or model" -v
```

Expected: all parts-related tests PASS.

- [ ] **Step 5: Run the full test suite to confirm everything passes together**

```bash
cd web_scrapers/junkyard_inventory_scrapers
JUNKYARD_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/junkyard_inventory \
PARTS_DATABASE_URL=postgresql://scrapestack:${POSTGRES_PASSWORD}@localhost:5433/parts_interchange \
pytest tests/test_db_foundation.py -v
```

Expected: all tests PASS. Output should include:

```
tests/test_db_foundation.py::test_junkyard_db_is_reachable PASSED
tests/test_db_foundation.py::test_parts_db_is_reachable PASSED
tests/test_db_foundation.py::test_locations_table_exists PASSED
tests/test_db_foundation.py::test_vehicles_table_exists PASSED
tests/test_db_foundation.py::test_mapping_rules_table_exists PASSED
tests/test_db_foundation.py::test_mapping_discrepancies_table_exists PASSED
tests/test_db_foundation.py::test_scrape_runs_table_exists PASSED
tests/test_db_foundation.py::test_vehicle_details_table_does_not_exist PASSED
tests/test_db_foundation.py::test_vehicles_has_car_id_columns PASSED
tests/test_db_foundation.py::test_vehicles_has_extras_column PASSED
tests/test_db_foundation.py::test_vehicles_has_flattened_detail_columns PASSED
tests/test_db_foundation.py::test_car_table_exists PASSED
tests/test_db_foundation.py::test_part_table_exists PASSED
tests/test_db_foundation.py::test_car_parts_table_exists PASSED
tests/test_db_foundation.py::test_make_table_exists PASSED
tests/test_db_foundation.py::test_model_table_exists PASSED

16 passed
```

- [ ] **Step 6: Commit**

```bash
cd parts_interchange
git add parts-loader-v2/src/config.py
git commit -m "feat: update loader-v2 defaults to target scrape_stack postgres (localhost:5433)"

cd ../web_scrapers
git add junkyard_inventory_scrapers/tests/test_db_foundation.py
git commit -m "test: add Phase 0 schema smoke tests — 16 pass"
```

---

## Self-Review

**Spec coverage check:**

- [x] Provision/extend PostgreSQL container — covered in Task 1 (extending the existing scrape_stack postgres via initdb + manual CREATE DATABASE)
- [x] Create `junkyard_inventory` database — Task 1
- [x] Create `parts_interchange` database — Task 1
- [x] Alembic migration for junkyard_inventory canonical schema — Tasks 3 + 4
- [x] VehicleDetail flattened into Vehicle — Task 2 + migration in Task 4
- [x] `extras JSONB` column — in models.py (Task 2) and migration (Task 4)
- [x] `car_id` / `car_id_resolved` / `car_id_method` / `car_id_confidence` columns — Task 2 + Task 4
- [x] `mapping_rules` table — Task 2 + Task 4
- [x] `mapping_discrepancies` table — Task 2 + Task 4
- [x] Apply parts_interchange schema — Task 5
- [x] Verify both schemas are queryable — Task 5 full smoke run (16 tests)
- [x] `vehicle_details` table confirmed absent — `test_vehicle_details_table_does_not_exist`

**Placeholder scan:** No TBDs, TODOs, or vague steps found.

**Type consistency:** `MappingDiscrepancy.resolved_by_rule_id` references `mapping_rules.id` — consistent with `MappingRule.__tablename__ = "mapping_rules"` in models.py and the migration. `Vehicle.location_id` → `locations.id` — consistent throughout.
