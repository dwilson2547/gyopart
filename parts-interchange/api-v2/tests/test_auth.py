import pytest
from httpx import AsyncClient


async def test_admin_route_rejects_missing_key(client: AsyncClient):
    response = await client.get("/v1/admin/junkyards")
    assert response.status_code == 403


async def test_admin_route_rejects_wrong_key(client: AsyncClient):
    response = await client.get("/v1/admin/junkyards", headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 403


async def test_worker_route_rejects_missing_key(client: AsyncClient):
    response = await client.put("/v1/worker/scrape-jobs/1/status", json={"status": "running"})
    assert response.status_code == 403
