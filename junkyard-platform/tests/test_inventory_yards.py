"""Yard browsing (inventory_api/yards.py) with a mocked engine."""
from datetime import datetime
from unittest.mock import MagicMock

from inventory_api import yards


def _engine(*results):
    conn = MagicMock()
    conn.execute.side_effect = results
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


def _mappings(rows):
    r = MagicMock()
    r.mappings.return_value.all.return_value = rows
    r.mappings.return_value.first.return_value = rows[0] if rows else None
    return r


def _yard(i, name, distance):
    return {"location_id": i, "name": name, "chain": None, "address": None, "city": None, "state": None,
            "zip_code": None, "phone": None, "lat": None, "lng": None, "last_seen_at": datetime(2026, 10, 12),
            "distance_miles": distance, "vehicle_count": 3, "new_this_week": 1, "catalogued_count": 2}


def test_list_yards_nearest_first_unlocated_last():
    engine, _ = _engine(_mappings([_yard(1, "Far", 200.0), _yard(2, "Calgary", None), _yard(3, "Near", 5.0)]))
    assert [y.name for y in yards.list_yards(engine, 42.6, -83.0)] == ["Near", "Far", "Calgary"]


def test_list_yards_without_zip_sorts_by_name():
    engine, conn = _engine(_mappings([_yard(1, "b", None), _yard(2, "A", None)]))
    assert [y.name for y in yards.list_yards(engine, None, None)] == ["A", "b"]
    assert "NULL::float" in str(conn.execute.call_args[0][0])


def test_facets_group_models_under_makes():
    engine, _ = _engine(_mappings([
        {"make": "FORD", "model": "F-150", "y0": 2004, "y1": 2014, "n": 5},
        {"make": "FORD", "model": "FLEX", "y0": 2009, "y1": 2012, "n": 2},
        {"make": "KIA", "model": None, "y0": 2015, "y1": 2015, "n": 1},
    ]))
    f = yards.yard_facets(engine, 55)
    assert [(m.make, m.count, [x.model for x in m.models]) for m in f.makes] == [
        ("FORD", 7, ["F-150", "FLEX"]), ("KIA", 1, [])]
    assert (f.year_min, f.year_max) == (2004, 2015)


def test_vehicles_filters_and_page():
    count = MagicMock(); count.scalar_one.return_value = 1
    rows = _mappings([{"vehicle_id": 9, "year": 2009, "make": "FORD", "model": "FLEX", "trim": "SEL", "row": "41",
                       "color": "RED", "vin": "2FMEK62C39BA22088", "arrival_date": datetime(2026, 10, 9),
                       "car_id": 8087, "car_id_candidates": [8087]}])
    engine, conn = _engine(count, rows)
    page = yards.yard_vehicles(engine, 55, "FORD", None, 2009, 50, 0)
    assert page.total == 1 and page.vehicles[0].car_id_candidates == [8087]
    sql, params = conn.execute.call_args_list[1][0]
    assert "make = :make" in str(sql) and "year = :year" in str(sql) and "model" not in params
