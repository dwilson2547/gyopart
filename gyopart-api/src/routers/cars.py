from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from src import vin as vinlib
from src.db import DbDep
from src.models import Car, Engine, Make, Model, Trim, Year
from src.schemas import CarDetailOut, VinDecodeOut

router = APIRouter(prefix="/v1", tags=["cars"])


def _car_query():
    return (
        select(
            Car.id.label("car_id"),
            Year.id.label("year_id"), Year.name.label("year"),
            Make.id.label("make_id"), Make.name.label("make"),
            Model.id.label("model_id"), Model.name.label("model"),
            Trim.id.label("trim_id"), Trim.name.label("trim"),
            Engine.id.label("engine_id"), Engine.name.label("engine"),
        )
        .join(Year, Year.id == Car.year_id)
        .join(Make, Make.id == Car.make_id)
        .join(Model, Model.id == Car.model_id)
        .outerjoin(Trim, Trim.id == Car.trim_id)
        .outerjoin(Engine, Engine.id == Car.engine_id)
    )


@router.get("/cars/{car_id}", response_model=CarDetailOut)
def get_car(car_id: int, db: DbDep):
    row = db.execute(_car_query().where(Car.id == car_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="car not found")
    return row


@router.get("/vin/{vin}", response_model=VinDecodeOut)
def decode_vin(vin: str, db: DbDep):
    """NHTSA decode of a VIN, plus the catalogue cars it narrows to (empty when the year/make/model isn't
    in the catalogue)."""
    vin = vin.strip().upper()
    if not vinlib.VIN_RE.match(vin):
        raise HTTPException(status_code=422, detail="VIN must be 17 letters/digits (no I, O or Q)")
    try:
        raw = vinlib.decode(vin)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"NHTSA unavailable: {exc}")

    info = vinlib.summary(raw)
    candidates = []
    narrowed_by: list[str] = []
    if info["year"] and info["make"] and info["model"]:
        rows = db.execute(
            _car_query().where(Year.name == info["year"], func.lower(Make.name) == info["make"].lower())
        ).mappings().all()
        by_id = {r["car_id"]: r for r in rows}
        narrowed = vinlib.narrow(raw, [
            vinlib.CatalogueRow(car_id=r["car_id"], model=r["model"], trim=r["trim"], engine=r["engine"])
            for r in rows
        ])
        candidates = [by_id[r.car_id] for r in narrowed.rows]
        narrowed_by = narrowed.narrowed_by
    return VinDecodeOut(vin=vin, decoded=info, candidates=candidates, narrowed_by=narrowed_by)
