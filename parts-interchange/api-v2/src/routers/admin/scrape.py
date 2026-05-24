import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.database import DbDep
from src.middleware.auth import require_admin_key
from src.models.junkyard import ScrapeConfig, ScrapeJob
from src.schemas.admin import ScrapeConfigIn, ScrapeJobOut

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("/scrape-configs")
async def list_scrape_configs(db: DbDep):
    result = await db.execute(select(ScrapeConfig).order_by(ScrapeConfig.id))
    return result.scalars().all()


@router.post("/scrape-configs", status_code=201)
async def create_scrape_config(payload: ScrapeConfigIn, db: DbDep):
    cfg = ScrapeConfig(**payload.model_dump())
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.put("/scrape-configs/{config_id}")
async def update_scrape_config(config_id: int, payload: ScrapeConfigIn, db: DbDep):
    result = await db.execute(select(ScrapeConfig).where(ScrapeConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/scrape-configs/{config_id}", status_code=204)
async def delete_scrape_config(config_id: int, db: DbDep):
    result = await db.execute(select(ScrapeConfig).where(ScrapeConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.delete(cfg)
    await db.commit()


@router.get("/scrape-jobs", response_model=list[ScrapeJobOut])
async def list_scrape_jobs(db: DbDep):
    result = await db.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(200))
    return result.scalars().all()


@router.post("/scrape-configs/{config_id}/trigger", response_model=ScrapeJobOut, status_code=201)
async def trigger_scrape(config_id: int, db: DbDep):
    from src.services.iggy import iggy_service
    result = await db.execute(select(ScrapeConfig).where(ScrapeConfig.id == config_id))
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    job = ScrapeJob(scrape_site_config_id=config_id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    try:
        await iggy_service.publish_scrape_job(
            job_id=job.id,
            config_id=cfg.id,
            site_type=cfg.site_type,
            url=cfg.url,
            triggered_by="admin",
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Iggy unavailable — job created but not queued")
    return job
