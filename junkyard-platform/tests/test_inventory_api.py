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


from unittest.mock import MagicMock, patch
from inventory_api.search import search_inventory

# dict stands in for RowMapping; both support row["key"] access

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
    mock_conn.execute.return_value.mappings.return_value.all.return_value = [fake_row]

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
    mock_conn.execute.return_value.mappings.return_value.all.return_value = rows

    results = search_inventory(
        engine=mock_engine, car_ids=[1, 2], lat=42.33, lng=-83.04, radius_miles=50.0
    )
    assert len(results) == 1
    assert len(results[0].matching_vehicles) == 2


def test_search_inventory_empty_result():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.mappings.return_value.all.return_value = []

    results = search_inventory(
        engine=mock_engine, car_ids=[1], lat=42.33, lng=-83.04, radius_miles=50.0
    )
    assert results == []


from starlette.testclient import TestClient


def _make_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.mappings.return_value.all.return_value = []
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


def test_search_invalid_car_id_format_returns_422():
    with patch("inventory_api.main._engine", _make_mock_engine()):
        client = _get_client()
        resp = client.get("/inventory/search?car_ids=abc,1&zip=48093&radius_miles=50")
    assert resp.status_code == 422


# ── integration tests (skipped without DB) ─────────────────────────────────

_JUNKYARD_URL = os.environ.get("JUNKYARD_DATABASE_URL", "")

skip_no_db = pytest.mark.skipif(
    not _JUNKYARD_URL,
    reason="JUNKYARD_DATABASE_URL not set — skipping integration tests",
)


@skip_no_db
def test_integration_search_returns_200():
    """Smoke test: verifies the endpoint connects and returns a valid response shape."""
    from inventory_api.main import app

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

    with TestClient(app) as client:
        resp = client.get("/inventory/search?car_ids=1&zip=00000&radius_miles=50")
    assert resp.status_code == 422
    assert "zip code not found" in resp.json()["detail"].lower()
