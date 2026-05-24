import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.database import DbDep
from src.middleware.auth import require_worker_key
from src.models.junkyard import ScrapeJob
from src.models.parts import Image, Manufacturer, Part
from src.models.vehicle import Car, Engine, Make, Model, Trim, Year, car_parts
from src.schemas.admin import ScrapeJobOut
from src.schemas.worker import CarBatchIn, ImageBatchIn, JobStatusIn, PartBatchIn

router = APIRouter(prefix="/v1/worker", tags=["worker"], dependencies=[Depends(require_worker_key)])


@router.put("/scrape-jobs/{job_id}/status", response_model=ScrapeJobOut)
async def update_job_status(job_id: int, payload: JobStatusIn, db: DbDep):
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = payload.status
    now = datetime.datetime.now(datetime.timezone.utc)
    if payload.status == "running":
        job.started_at = now
    elif payload.status in ("completed", "failed"):
        job.completed_at = now
    if payload.error_message:
        job.error_message = payload.error_message
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/parts", status_code=201)
async def upsert_parts(payload: PartBatchIn, db: DbDep):
    for item in payload.parts:
        result = await db.execute(select(Part).where(Part.part_number == item.part_number))
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in item.model_dump(exclude={"part_number"}, exclude_none=True).items():
                setattr(existing, k, v)
        else:
            db.add(Part(**item.model_dump()))
    await db.commit()
    return {"upserted": len(payload.parts)}


@router.post("/images", status_code=201)
async def upsert_images(payload: ImageBatchIn, db: DbDep):
    for item in payload.images:
        result = await db.execute(select(Image).where(Image.name == item.name))
        if not result.scalar_one_or_none():
            db.add(Image(**item.model_dump()))
    await db.commit()
    return {"upserted": len(payload.images)}


@router.post("/cars", status_code=201)
async def upsert_cars(payload: CarBatchIn, db: DbDep):
    for item in payload.cars:
        yr = (await db.execute(select(Year).where(Year.name == item.year))).scalar_one_or_none() or Year(name=item.year)
        mk = (await db.execute(select(Make).where(Make.select_value == item.make_select_value))).scalar_one_or_none() or Make(name=item.make_ui, select_value=item.make_select_value)
        db.add_all([yr, mk])
        await db.flush()

        mdl = (await db.execute(select(Model).where(Model.select_value == item.model_select_value, Model.make_id == mk.id))).scalar_one_or_none()
        if not mdl:
            mdl = Model(name=item.model_ui, select_value=item.model_select_value, make=mk)
        trm = (await db.execute(select(Trim).where(Trim.select_value == item.trim_select_value))).scalar_one_or_none() or Trim(name=item.trim_ui, select_value=item.trim_select_value)
        eng = (await db.execute(select(Engine).where(Engine.select_value == item.engine_select_value))).scalar_one_or_none() or Engine(name=item.engine_ui, select_value=item.engine_select_value)
        db.add_all([mdl, trm, eng])
        await db.flush()

        car = (await db.execute(select(Car).where(
            Car.year_id == yr.id, Car.make_id == mk.id, Car.model_id == mdl.id,
            Car.trim_id == trm.id, Car.engine_id == eng.id
        ))).scalar_one_or_none()
        if not car:
            car = Car(year=yr, make=mk, model=mdl, trim=trm, engine=eng,
                      manufacturer_id=item.manufacturer_id, car_id=item.car_id,
                      vehicle_id=item.vehicle_id, base_url=item.base_url)
            db.add(car)
            await db.flush()

        for pn in item.part_numbers:
            p = (await db.execute(select(Part).where(Part.part_number == pn))).scalar_one_or_none()
            if p:
                await db.execute(
                    car_parts.insert().prefix_with("OR IGNORE").values(car_id=car.id, part_id=p.id)
                )

    await db.commit()
    return {"processed": len(payload.cars)}
