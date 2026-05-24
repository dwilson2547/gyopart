from fastapi import APIRouter, Query
from sqlalchemy import select
from src.database import DbDep
from src.models.vehicle import Car, Engine, Make, Model, Trim, Year
from src.schemas.vehicle import CarOut, EngineOut, MakeOut, ModelOut, TrimOut, YearOut

router = APIRouter(prefix="/v1/vehicles", tags=["vehicles"])


@router.get("/years", response_model=list[YearOut])
async def get_years(db: DbDep):
    result = await db.execute(select(Year).order_by(Year.name.desc()))
    return result.scalars().all()


@router.get("/makes", response_model=list[MakeOut])
async def get_makes(db: DbDep, year_id: int = Query(...)):
    sub = select(Car.make_id).where(Car.year_id == year_id).distinct()
    result = await db.execute(select(Make).where(Make.id.in_(sub)))
    return result.scalars().all()


@router.get("/models", response_model=list[ModelOut])
async def get_models(db: DbDep, year_id: int = Query(...), make_id: int = Query(...)):
    sub = select(Car.model_id).where(Car.year_id == year_id, Car.make_id == make_id).distinct()
    result = await db.execute(select(Model).where(Model.id.in_(sub)))
    return result.scalars().all()


@router.get("/trims", response_model=list[TrimOut])
async def get_trims(db: DbDep, year_id: int = Query(...), make_id: int = Query(...), model_id: int = Query(...)):
    sub = select(Car.trim_id).where(Car.year_id == year_id, Car.make_id == make_id, Car.model_id == model_id).distinct()
    result = await db.execute(select(Trim).where(Trim.id.in_(sub)))
    return result.scalars().all()


@router.get("/engines", response_model=list[EngineOut])
async def get_engines(db: DbDep, year_id: int = Query(...), make_id: int = Query(...), model_id: int = Query(...), trim_id: int = Query(...)):
    sub = select(Car.engine_id).where(
        Car.year_id == year_id, Car.make_id == make_id,
        Car.model_id == model_id, Car.trim_id == trim_id
    ).distinct()
    result = await db.execute(select(Engine).where(Engine.id.in_(sub)))
    return result.scalars().all()


@router.get("/cars", response_model=list[CarOut])
async def get_cars(db: DbDep, year_id: int = Query(...), make_id: int = Query(...), model_id: int = Query(...), trim_id: int = Query(...), engine_id: int = Query(...)):
    result = await db.execute(
        select(Car).where(
            Car.year_id == year_id, Car.make_id == make_id,
            Car.model_id == model_id, Car.trim_id == trim_id,
            Car.engine_id == engine_id
        )
    )
    return result.scalars().all()
