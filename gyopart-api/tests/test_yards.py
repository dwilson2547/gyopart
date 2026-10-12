from unittest.mock import MagicMock

import httpx

from src.routers import yards as yards_router


def _resp(status, payload):
    r = MagicMock(status_code=status)
    r.json.return_value = payload
    return r


def _car(car_id):
    return {"car_id": car_id, "year_id": 1, "year": "2009", "make_id": 2, "make": "Ford", "model_id": 3,
            "model": "Flex", "trim_id": 4, "trim": "SEL", "engine_id": 5, "engine": "3.5L V6 - Gas"}


def test_vehicles_get_named_candidates(client, mock_db, mocker):
    mocker.patch.object(yards_router.httpx, "get", return_value=_resp(200, {
        "total": 2, "limit": 50, "offset": 0, "vehicles": [
            {"vehicle_id": 1, "year": 2009, "make": "FORD", "model": "FLEX", "trim": "SEL", "row": "41",
             "color": "RED", "vin": None, "arrival_date": None, "car_id": 8087, "car_id_candidates": [8087]},
            {"vehicle_id": 2, "year": 2026, "make": "KIA", "model": "EV9", "trim": None, "row": "2",
             "color": None, "vin": None, "arrival_date": None, "car_id": None, "car_id_candidates": []},
        ]}))
    mock_db.execute.return_value.mappings.return_value.all.return_value = [_car(8087)]
    data = client.get("/v1/yards/55/vehicles?make=FORD").json()
    assert data["vehicles"][0]["candidates"][0]["trim"] == "SEL"
    assert data["vehicles"][1]["candidates"] == []
    params = yards_router.httpx.get.call_args.kwargs["params"]
    assert params["make"] == "FORD" and "model" not in params


def test_yard_404_and_inventory_down(client, mocker):
    mocker.patch.object(yards_router.httpx, "get", return_value=_resp(404, {"detail": "yard not found"}))
    assert client.get("/v1/yards/9").status_code == 404
    mocker.patch.object(yards_router.httpx, "get", side_effect=httpx.ConnectError("down"))
    assert client.get("/v1/yards").status_code == 502
