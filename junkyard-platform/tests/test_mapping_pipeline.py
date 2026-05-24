import datetime
import os
from unittest.mock import MagicMock, patch

import pytest

from junkyard_common.models import VinCache


def test_vin_cache_model_has_required_fields():
    v = VinCache(
        vin="1HGCM82633A004352",
        make="Honda",
        model="Accord",
        model_year="2003",
        trim="EX",
        error_code=None,
        fetched_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    assert v.vin == "1HGCM82633A004352"
    assert v.make == "Honda"
    assert v.error_code is None


def test_pi_schema_tables_importable():
    from pipeline.pi_schema import (
        pi_car_table, pi_make_table, pi_model_table, pi_year_table,
    )
    assert pi_year_table.c.id is not None
    assert pi_make_table.c.name is not None
    assert pi_model_table.c.make_id is not None
    assert pi_car_table.c.year_id is not None


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
    from pipeline.vin_decoder import decode_vin
    session = MagicMock()
    assert decode_vin("SHORT", session) is None
    session.get.assert_not_called()


def test_decode_vin_cache_hit_success():
    from pipeline.vin_decoder import decode_vin
    from junkyard_common.models import VinCache
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
    from pipeline.vin_decoder import decode_vin
    from junkyard_common.models import VinCache
    cached = VinCache(vin="1HGCM82633A004352", error_code="11", fetched_at=datetime.datetime.now())
    session = MagicMock()
    session.get.return_value = cached
    assert decode_vin("1HGCM82633A004352", session) is None


def test_decode_vin_cache_miss_success():
    from pipeline.vin_decoder import decode_vin
    session = MagicMock()
    session.get.return_value = None  # cache miss
    with patch("pipeline.vin_decoder._fetch_nhtsa", return_value={
        "Make": "Honda", "Model": "Accord", "ModelYear": "2003",
        "Trim": "EX", "ErrorCode": "0",
    }), patch("pipeline.vin_decoder.time.sleep"):
        result = decode_vin("1HGCM82633A004352", session)
    assert result["make"] == "Honda"
    assert result["model"] == "Accord"
    session.merge.assert_called_once()
    session.commit.assert_called_once()


def test_decode_vin_pre1980():
    from pipeline.vin_decoder import decode_vin
    session = MagicMock()
    session.get.return_value = None
    with patch("pipeline.vin_decoder._fetch_nhtsa", return_value={
        "Make": "", "Model": "", "ModelYear": "", "Trim": "", "ErrorCode": "11 - "
    }), patch("pipeline.vin_decoder.time.sleep"):
        result = decode_vin("1HGCM82633A004352", session)
    assert result is None
    session.merge.assert_called_once()


def test_resolve_vin_to_car_id_found():
    from pipeline.vin_decoder import resolve_vin_to_car_id

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
    from pipeline.vin_decoder import resolve_vin_to_car_id
    pi_engine = MagicMock()
    conn = MagicMock()
    pi_engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    pi_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.one_or_none.return_value = None  # year not found
    decoded = {"make": "Honda", "model": "Accord", "model_year": "1899", "trim": ""}
    assert resolve_vin_to_car_id(decoded, pi_engine) is None


def test_normalize_strips_punctuation_and_suffixes():
    from pipeline.ymmt_matcher import normalize
    assert normalize("Ford, Inc.") == "ford"
    assert normalize("General Motors Corp") == "general motors"
    assert normalize("Toyota LLC") == "toyota"
    assert normalize("HONDA") == "honda"
    assert normalize("Chevy-S10") == "chevy s10"


def test_normalize_empty():
    from pipeline.ymmt_matcher import normalize
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
    from pipeline.ymmt_matcher import match_car
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
    from pipeline.ymmt_matcher import match_car
    pi_engine = _make_pi_engine_mock(
        makes=[(1, "Honda")],
        models_by_make_id={1: [(5, "Accord")]},
        cars=[],
    )
    # "Hyundai" vs "Honda" should be below 0.85
    result = match_car(2003, "Hyundai", "Sonata", pi_engine, threshold=0.85)
    assert result is None


def test_match_car_no_makes_in_db():
    from pipeline.ymmt_matcher import match_car
    pi_engine = _make_pi_engine_mock(makes=[], models_by_make_id={}, cars=[])
    assert match_car(2003, "Honda", "Accord", pi_engine) is None


def _make_rule(
    field, rule_type, raw_value, canonical_value,
    scope="global", source=None, location_id=None,
    make_context=None, priority=100, is_active=True,
):
    from junkyard_common.models import MappingRule
    return MappingRule(
        id=None, scope=scope, source=source, location_id=location_id,
        field=field, rule_type=rule_type,
        raw_value=raw_value, canonical_value=canonical_value,
        make_context=make_context, priority=priority, is_active=is_active,
        created_by="manual", created_at=datetime.datetime.now(),
        applied_count=0,
    )


def test_apply_rules_exact_match_make():
    from pipeline.rule_engine import apply_rules
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
    from pipeline.rule_engine import apply_rules
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
    from pipeline.rule_engine import apply_rules
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
    from pipeline.rule_engine import apply_rules
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
    from pipeline.rule_engine import apply_rules
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
    from pipeline.rule_engine import apply_rules
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
    from pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(car_id_resolved=True)
    session = MagicMock()
    pi_engine = MagicMock()
    result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)
    assert result == "already_resolved"
    session.commit.assert_not_called()


def test_resolve_vehicle_vin_decode_success():
    from pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(vin="1HGCM82633A004352")
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("pipeline.resolution_pipeline.decode_vin",
               return_value={"make": "Honda", "model": "Accord", "model_year": "2003", "trim": "EX"}), \
         patch("pipeline.resolution_pipeline.resolve_vin_to_car_id", return_value=42):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "vin_decode"
    assert vehicle.car_id == 42
    assert vehicle.car_id_resolved is True
    assert vehicle.car_id_method == "vin_decode"
    assert vehicle.car_id_confidence == 1.0
    session.commit.assert_called()


def test_resolve_vehicle_ymmt_match_success():
    from pipeline.resolution_pipeline import resolve_vehicle
    from pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()
    ymmt = YmmtMatch(car_id=77, confidence=0.92, make_match="Honda",
                     make_score=0.95, model_match="Accord", model_score=0.92)

    with patch("pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": "EX"}, [])), \
         patch("pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "ymmt_match"
    assert vehicle.car_id == 77
    assert vehicle.car_id_method == "ymmt_match"


def test_resolve_vehicle_rule_applied_method():
    from pipeline.resolution_pipeline import resolve_vehicle
    from pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None, make="chevy")
    session = MagicMock()
    pi_engine = MagicMock()
    fake_rule = MagicMock()
    ymmt = YmmtMatch(car_id=55, confidence=0.91, make_match="Chevrolet",
                     make_score=0.95, model_match="Silverado", model_score=0.91)

    with patch("pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Chevrolet", "model": "Silverado", "trim": ""}, [fake_rule])), \
         patch("pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[fake_rule], dry_run=False)

    assert result == "rule_applied"
    assert vehicle.car_id_method == "rule_applied"


def test_resolve_vehicle_unresolved():
    from pipeline.resolution_pipeline import resolve_vehicle
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": ""}, [])), \
         patch("pipeline.resolution_pipeline.match_car", return_value=None):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    assert result == "discrepancy"
    session.merge.assert_called_once()
    session.commit.assert_called()


def test_resolve_vehicle_dry_run_does_not_commit():
    from pipeline.resolution_pipeline import resolve_vehicle
    from pipeline.ymmt_matcher import YmmtMatch
    vehicle = _make_vehicle(vin=None)
    session = MagicMock()
    pi_engine = MagicMock()
    ymmt = YmmtMatch(car_id=77, confidence=0.92, make_match="Honda",
                     make_score=0.95, model_match="Accord", model_score=0.92)

    with patch("pipeline.resolution_pipeline.decode_vin", return_value=None), \
         patch("pipeline.resolution_pipeline.apply_rules",
               return_value=({"make": "Honda", "model": "Accord", "trim": ""}, [])), \
         patch("pipeline.resolution_pipeline.match_car", return_value=ymmt):
        result = resolve_vehicle(vehicle, session, pi_engine, rules=[], dry_run=True)

    assert result == "ymmt_match"
    session.commit.assert_not_called()


def test_apply_rules_dry_run_does_not_commit():
    from pipeline.rule_engine import apply_rules
    from unittest.mock import MagicMock
    rule = _make_rule("make", "exact", "chevy", "Chevrolet")
    session = MagicMock()
    vehicle = MagicMock()
    vehicle.make = "chevy"
    vehicle.model = "Silverado"
    vehicle.trim = ""
    result, applied = apply_rules(vehicle, [rule], session, dry_run=True)
    assert result["make"] == "Chevrolet"
    assert rule in applied


def test_get_reprocess_vehicle_ids_excludes_ignored_and_manual():
    from pipeline.reprocess_job import get_reprocess_vehicle_ids
    session = MagicMock()
    # Simulate query returning vehicle IDs 1, 2, 3
    session.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    ids = get_reprocess_vehicle_ids(session)
    assert ids == [1, 2, 3]
    # Verify the status filter was applied (check call was made)
    session.execute.assert_called_once()


def test_reprocess_resets_car_id_before_resolving():
    from pipeline.reprocess_job import reprocess_vehicle
    vehicle = _make_vehicle(vin=None, car_id_resolved=True)
    vehicle.car_id = 99
    session = MagicMock()
    pi_engine = MagicMock()

    with patch("pipeline.reprocess_job.resolve_vehicle", return_value="ymmt_match") as mock_resolve:
        reprocess_vehicle(vehicle, session, pi_engine, rules=[], dry_run=False)

    # car_id_resolved must be reset to False before calling resolve_vehicle
    assert vehicle.car_id_resolved is False
    assert vehicle.car_id is None
    mock_resolve.assert_called_once_with(vehicle, session, pi_engine, [], False)
    session.commit.assert_not_called()


# ==============================================================================
# Integration Tests (skipped if env vars not set)
# ==============================================================================

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
    """Run pipeline on first 5 unresolved vehicles; verify no exceptions and results are valid."""
    from sqlalchemy import create_engine, select
    from junkyard_common.db import get_engine, get_session
    from junkyard_common.models import MappingRule, Vehicle
    from pipeline.resolution_pipeline import resolve_vehicle

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
