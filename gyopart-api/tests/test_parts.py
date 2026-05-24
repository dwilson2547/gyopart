from unittest.mock import MagicMock


def _part(id=1, title="Engine Air Filter", part_number="A-100", description=None, other_names=None):
    m = MagicMock()
    m.id = id
    m.title = title
    m.part_number = part_number
    m.description = description
    m.other_names = other_names
    return m


def test_get_parts_requires_car_id(client, mock_db):
    resp = client.get("/v1/parts")
    assert resp.status_code == 422


def test_get_parts(client, mock_db):
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [_part()]
    mock_db.execute.side_effect = [count_result, items_result]
    resp = client.get("/v1/parts?car_id=99")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Engine Air Filter"
    assert data["page"] == 1


def test_get_part_by_id(client, mock_db):
    mock_db.get.return_value = _part(id=5, title="Alternator")
    resp = client.get("/v1/parts/5")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Alternator"


def test_get_part_not_found(client, mock_db):
    mock_db.get.return_value = None
    resp = client.get("/v1/parts/999")
    assert resp.status_code == 404


def test_get_compatible_car_ids(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    resp = client.get("/v1/parts/5/compatible-cars")
    assert resp.status_code == 200
    assert resp.json() == [1, 2, 3]


def test_get_parts_filter_param_accepted(client, mock_db):
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [count_result, items_result]
    resp = client.get("/v1/parts?car_id=1&filter=filter&page=2")
    assert resp.status_code == 200
    assert resp.json()["page"] == 2
