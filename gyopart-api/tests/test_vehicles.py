from unittest.mock import MagicMock


def _obj(**kwargs):
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def test_get_years(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _obj(id=1, name="2022"), _obj(id=2, name="2021"),
    ]
    resp = client.get("/v1/vehicles/years")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "2022"


def test_get_makes_requires_year_id(client, mock_db):
    resp = client.get("/v1/vehicles/makes")
    assert resp.status_code == 422


def test_get_makes(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="Toyota")]
    resp = client.get("/v1/vehicles/makes?year_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Toyota"


def test_get_models(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="Camry", make_id=1)]
    resp = client.get("/v1/vehicles/models?year_id=1&make_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Camry"


def test_get_trims(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="LE")]
    resp = client.get("/v1/vehicles/trims?year_id=1&make_id=1&model_id=1")
    assert resp.status_code == 200


def test_get_engines(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="2.5L 4-cyl")]
    resp = client.get("/v1/vehicles/engines?year_id=1&make_id=1&model_id=1&trim_id=1")
    assert resp.status_code == 200


def test_get_cars(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _obj(id=99, year_id=1, make_id=1, model_id=1, trim_id=1, engine_id=1)
    ]
    resp = client.get("/v1/vehicles/cars?year_id=1&make_id=1&model_id=1&trim_id=1&engine_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 99


def test_get_cars_requires_all_params(client, mock_db):
    resp = client.get("/v1/vehicles/cars?year_id=1&make_id=1")
    assert resp.status_code == 422
