from unittest.mock import MagicMock

import httpx

from src import vin as vinlib

SEBRING = {"ModelYear": "2010", "Make": "CHRYSLER", "Model": "Sebring", "Trim": "LX",
           "DisplacementL": "2.4", "EngineCylinders": "4", "FuelTypePrimary": "Gasoline", "ErrorCode": "0"}


def _car(car_id, trim, engine, model="Sebring"):
    return {"car_id": car_id, "year_id": 1, "year": "2010", "make_id": 2, "make": "Chrysler", "model_id": 3,
            "model": model, "trim_id": car_id * 10, "trim": trim, "engine_id": car_id * 100, "engine": engine}


def test_get_car(client, mock_db):
    mock_db.execute.return_value.mappings.return_value.first.return_value = _car(1, "LX", "2.4L L4 - Gas")
    resp = client.get("/v1/cars/1")
    assert resp.status_code == 200
    assert resp.json()["engine"] == "2.4L L4 - Gas"


def test_get_car_404(client, mock_db):
    mock_db.execute.return_value.mappings.return_value.first.return_value = None
    assert client.get("/v1/cars/9").status_code == 404


def test_vin_rejects_bad_vin(client):
    assert client.get("/v1/vin/1C3CC4FBXAN19747").status_code == 422      # 16 chars
    assert client.get("/v1/vin/1C3CC4FBXAN19747O").status_code == 422     # contains O


def test_vin_decodes_and_narrows(client, mock_db, mocker):
    mocker.patch.object(vinlib, "decode", return_value=SEBRING)
    mock_db.execute.return_value.mappings.return_value.all.return_value = [
        _car(1, "LX", "2.4L L4 - Gas"), _car(2, "Touring", "2.4L L4 - Gas"), _car(3, "Touring", "2.7L V6 - Gas"),
        _car(4, "LX", "3.3L V6 - Gas", model="Town & Country"),
    ]
    data = client.get("/v1/vin/1c3cc4fbxan197479").json()
    assert data["vin"] == "1C3CC4FBXAN197479"
    assert data["decoded"]["make"] == "CHRYSLER"
    assert data["decoded"]["error_text"] is None
    assert [c["car_id"] for c in data["candidates"]] == [1]
    assert data["narrowed_by"] == ["engine", "trim"]


def test_vin_nhtsa_down_is_502(client, mocker):
    mocker.patch.object(vinlib, "decode", side_effect=httpx.ConnectError("boom"))
    assert client.get("/v1/vin/1C3CC4FBXAN197479").status_code == 502


def test_narrow_keeps_set_when_filter_would_empty_it():
    rows = [vinlib.CatalogueRow(1, "Sebring", "LX", "2.4L L4 - Gas"),
            vinlib.CatalogueRow(2, "Sebring", "Touring", "2.4L L4 - Gas")]
    assert [r.car_id for r in vinlib.narrow(dict(SEBRING, Trim="Sport"), rows).rows] == [1, 2]
    assert vinlib.name_key("Town and Country") == vinlib.name_key("Town & Country")
