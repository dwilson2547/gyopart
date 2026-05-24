import pytest
from httpx import AsyncClient
from tests.conftest import ADMIN_HEADERS


async def test_list_junkyards_requires_auth(client: AsyncClient):
    response = await client.get("/v1/admin/junkyards")
    assert response.status_code == 403


async def test_create_junkyard(client: AsyncClient):
    payload = {"name": "LKQ Fontana", "city": "Fontana", "state": "CA", "lat": 34.09, "lng": -117.43}
    response = await client.post("/v1/admin/junkyards", json=payload, headers=ADMIN_HEADERS)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "LKQ Fontana"
    assert data["id"] is not None


async def test_update_junkyard(client: AsyncClient):
    create = await client.post("/v1/admin/junkyards", json={"name": "OldName"}, headers=ADMIN_HEADERS)
    jy_id = create.json()["id"]
    response = await client.put(f"/v1/admin/junkyards/{jy_id}", json={"name": "NewName"}, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert response.json()["name"] == "NewName"


async def test_delete_junkyard(client: AsyncClient):
    create = await client.post("/v1/admin/junkyards", json={"name": "ToDelete"}, headers=ADMIN_HEADERS)
    jy_id = create.json()["id"]
    response = await client.delete(f"/v1/admin/junkyards/{jy_id}", headers=ADMIN_HEADERS)
    assert response.status_code == 204


async def test_create_scrape_config(client: AsyncClient):
    jy = await client.post("/v1/admin/junkyards", json={"name": "TestYard"}, headers=ADMIN_HEADERS)
    jy_id = jy.json()["id"]
    payload = {"junkyard_id": jy_id, "site_type": "lkq", "url": "https://lkq.example.com", "scrape_interval_hours": 12}
    response = await client.post("/v1/admin/scrape-configs", json=payload, headers=ADMIN_HEADERS)
    assert response.status_code == 201
    assert response.json()["site_type"] == "lkq"
