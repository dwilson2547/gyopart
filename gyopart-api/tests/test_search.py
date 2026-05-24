import httpx
from unittest.mock import MagicMock, patch


def _yard():
    return {
        "location_id": 1, "name": "Pick-n-Pull Detroit", "address": "123 Main St",
        "city": "Detroit", "state": "MI", "zip_code": "48201",
        "phone": "555-1234", "distance_miles": 12.5,
        "matching_vehicles": [
            {"vehicle_id": 42, "year": 2018, "make": "Toyota", "model": "Camry",
             "trim": "LE", "row": "A14", "car_id": 99}
        ],
    }


def test_search_requires_part_id_and_zip(client, mock_db):
    resp = client.get("/v1/search")
    assert resp.status_code == 422


def test_search_zip_must_be_5_chars(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1]
    resp = client.get("/v1/search?part_id=1&zip=123")
    assert resp.status_code == 422


def test_search_no_compatible_cars_returns_empty(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    resp = client.get("/v1/search?part_id=1&zip=48093")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_calls_inventory_api_with_car_ids(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [_yard()]}
    mock_resp.raise_for_status = MagicMock()

    with patch("src.routers.search.httpx.get", return_value=mock_resp) as mock_get:
        resp = client.get("/v1/search?part_id=1&zip=48093&radius_miles=25")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Pick-n-Pull Detroit"
    assert data["results"][0]["distance_miles"] == 12.5
    assert data["results"][0]["matching_vehicles"][0]["make"] == "Toyota"

    params = mock_get.call_args.kwargs["params"]
    assert params["car_ids"] == "1,2,3"
    assert params["zip"] == "48093"
    assert params["radius_miles"] == 25.0


def test_search_returns_502_on_inventory_service_error(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1]
    with patch("src.routers.search.httpx.get", side_effect=httpx.ConnectError("refused")):
        resp = client.get("/v1/search?part_id=1&zip=48093")
    assert resp.status_code == 502
