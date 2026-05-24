"""
Integration smoke tests for Phase 0 database foundation.

Requires:
  JUNKYARD_DATABASE_URL=postgresql://scrapestack:<pass>@localhost:5433/junkyard_inventory
  PARTS_DATABASE_URL=postgresql://scrapestack:<pass>@localhost:5433/parts_interchange

Run from junkyard_platform/:
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
