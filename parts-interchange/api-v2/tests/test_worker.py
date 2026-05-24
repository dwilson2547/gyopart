import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.junkyard import ScrapeConfig, ScrapeJob
from tests.conftest import WORKER_HEADERS


@pytest_asyncio.fixture
async def seed_job(db: AsyncSession):
    cfg = ScrapeConfig(site_type="acura", url="https://acura.example.com")
    db.add(cfg)
    await db.flush()
    job = ScrapeJob(scrape_site_config_id=cfg.id, status="pending")
    db.add(job)
    await db.commit()
    return job


async def test_update_job_status_requires_auth(client: AsyncClient, seed_job):
    response = await client.put(f"/v1/worker/scrape-jobs/{seed_job.id}/status", json={"status": "running"})
    assert response.status_code == 403


async def test_update_job_status_running(client: AsyncClient, seed_job):
    response = await client.put(
        f"/v1/worker/scrape-jobs/{seed_job.id}/status",
        json={"status": "running"},
        headers=WORKER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["started_at"] is not None


async def test_update_job_status_completed(client: AsyncClient, seed_job):
    await client.put(f"/v1/worker/scrape-jobs/{seed_job.id}/status", json={"status": "running"}, headers=WORKER_HEADERS)
    response = await client.put(
        f"/v1/worker/scrape-jobs/{seed_job.id}/status",
        json={"status": "completed"},
        headers=WORKER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


async def test_update_job_status_failed(client: AsyncClient, seed_job):
    response = await client.put(
        f"/v1/worker/scrape-jobs/{seed_job.id}/status",
        json={"status": "failed", "error_message": "connection timeout"},
        headers=WORKER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["error_message"] == "connection timeout"
