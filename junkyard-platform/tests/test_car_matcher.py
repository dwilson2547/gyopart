from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.car_matcher import (
    decoded_engine, decoded_vehicle_fields, match_decoded, parse_catalogue_engine,
)

# 2010 Chrysler Sebring as NHTSA decodes it (US Auto Supply feed, 2026-10-12)
SEBRING = {"VIN": "1C3CC4FBXAN197479", "Make": "CHRYSLER", "Model": "Sebring", "ModelYear": "2010", "Trim": "LX",
           "DisplacementL": "2.4", "EngineCylinders": "4", "FuelTypePrimary": "Gasoline",
           "DriveType": "FWD/Front-Wheel Drive", "BodyClass": "Sedan/Saloon", "Doors": "4", "Turbo": "No"}


def _pi_engine(rows):
    conn = MagicMock()
    conn.execute.return_value.all.return_value = [SimpleNamespace(id=i, trim=t, engine=e) for i, t, e in rows]
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine


def test_parse_catalogue_engine():
    assert parse_catalogue_engine("2.4L L4 - Gas").__dict__ == {"displacement_l": 2.4, "cylinders": 4, "fuel": "gas"}
    assert parse_catalogue_engine("2.7L V6 - Flex").fuel == "flex"
    assert parse_catalogue_engine("3.5L V6 - Electric/Gas").fuel == "hybrid"
    assert parse_catalogue_engine("1.8L L4 - FULL HYBRID EV-GAS (FHEV)").fuel == "hybrid"
    assert parse_catalogue_engine("6.7L V8 - Diesel").fuel == "diesel"
    assert parse_catalogue_engine("weird").displacement_l is None


def test_decoded_engine_flex_from_secondary_fuel():
    raw = dict(SEBRING, DisplacementL="2.7", EngineCylinders="6", FuelTypeSecondary="Ethanol (E85)")
    assert decoded_engine(raw).__dict__ == {"displacement_l": 2.7, "cylinders": 6, "fuel": "flex"}


def test_match_narrows_by_engine_fuel_and_trim_to_exact():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas"), (3, "Touring", "2.7L V6 - Gas"),
            (4, "Touring", "2.7L V6 - Flex"), (5, "Limited", "3.5L V6 - Gas")]
    m = match_decoded(SEBRING, _pi_engine(rows))
    assert m.candidates == [1]
    assert m.exact
    assert m.narrowed_by == ["engine", "trim"]


def test_match_keeps_candidates_when_trim_unknown():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas"), (3, "Touring", "2.7L V6 - Gas")]
    m = match_decoded(dict(SEBRING, Trim=""), _pi_engine(rows))
    assert m.candidates == [1, 2]
    assert not m.exact


def test_match_ignores_a_filter_that_would_empty_the_set():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas")]
    m = match_decoded(dict(SEBRING, Trim="Sport"), _pi_engine(rows))
    assert m.candidates == [1, 2]


def test_match_empty_when_ymm_not_in_catalogue():
    assert match_decoded(SEBRING, _pi_engine([])).candidates == []
    assert match_decoded(dict(SEBRING, Model=""), _pi_engine([(1, "LX", "2.4L L4 - Gas")])).candidates == []


def test_decoded_vehicle_fields():
    assert decoded_vehicle_fields(SEBRING) == {
        "engine_size": 2.4, "engine_cylinders": 4, "fuel_type": "G", "engine_aspiration": "N/A",
        "drive_type": "FWD", "body_type": "Sedan/Saloon", "doors": 4, "trim": "LX",
    }
