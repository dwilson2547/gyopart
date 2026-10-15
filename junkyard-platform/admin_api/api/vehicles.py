"""One vehicle (design §2.4): find it, see why it did or didn't match, re-match it, match it by hand, or
re-scrape its yard through scrape-job-manager."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from junkyard_common.models import Location, MappingDiscrepancy, Vehicle, VinCache
from pipeline.pi_schema import (
    pi_car_table, pi_engine_table, pi_make_table, pi_model_table, pi_trim_table, pi_year_table,
)

from . import scrapejobs
from .common import engines, requeue

router = APIRouter(prefix="/api", tags=["vehicles"])
V, D = Vehicle, MappingDiscrepancy

# Yard columns shown on the page (the matching columns are shown separately).
_YARD_FIELDS = ("year", "make", "model", "trim", "vin", "row", "color", "arrival_date", "mileage", "vehicle_type",
                "body_type", "body_sub_type", "doors", "style", "drive_type", "fuel_type", "engine_block",
                "engine_cylinders", "engine_size", "engine_aspiration", "trans_type", "trans_speeds",
                "preview_image_url", "first_seen_at", "last_seen_at", "detail_fetched_at")


def _iso(v):
    return v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v


def describe_cars(pi, car_ids: list[int]) -> list[dict]:
    """Catalogue cars by id: year make model trim engine."""
    if not car_ids:
        return []
    with pi.connect() as conn:
        rows = conn.execute(
            select(pi_car_table.c.id, pi_year_table.c.name, pi_make_table.c.name, pi_model_table.c.name,
                   pi_trim_table.c.name, pi_engine_table.c.name)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id)
            .join(pi_model_table, pi_model_table.c.id == pi_car_table.c.model_id)
            .outerjoin(pi_trim_table, pi_trim_table.c.id == pi_car_table.c.trim_id)
            .outerjoin(pi_engine_table, pi_engine_table.c.id == pi_car_table.c.engine_id)
            .where(pi_car_table.c.id.in_(car_ids))
        ).all()
    by_id = {r[0]: {"id": r[0], "year": r[1], "make": r[2], "model": r[3], "trim": r[4], "engine": r[5]} for r in rows}
    return [by_id.get(i, {"id": i, "missing": True}) for i in car_ids]


def _row(v: Vehicle, location: str | None) -> dict:
    return {"id": v.id, "source": v.source, "stock": v.source_key, "location": location, "year": v.year,
            "make": v.make, "model": v.model, "trim": v.trim, "vin": v.vin, "matched": bool(v.car_id_resolved),
            "active": bool(v.is_active)}


@router.get("/vehicles/search")
def search(q: str = Query(..., min_length=2), eng=Depends(engines)):
    term = q.strip()
    conds = [func.upper(V.source_key) == term.upper()]
    if len(term) >= 5:
        conds += [V.vin.ilike(f"{term}%"), V.vin.ilike(f"%{term}")]
    if term.isdigit():
        conds.append(V.id == int(term))
    with Session(eng[0]) as s:
        rows = s.execute(select(V, Location.name).join(Location, Location.id == V.location_id)
                         .where(or_(*conds)).order_by(V.is_active.desc(), V.last_seen_at.desc()).limit(20)).all()
    return [_row(v, loc) for v, loc in rows]


@router.get("/vehicles/{vehicle_id}")
def vehicle(vehicle_id: int, eng=Depends(engines)):
    ji, pi = eng
    with Session(ji) as s:
        found = s.execute(select(V, Location.name).join(Location, Location.id == V.location_id)
                          .where(V.id == vehicle_id)).first()
        if found is None:
            raise HTTPException(404, "no such vehicle")
        v, location = found
        d = s.execute(select(D).where(D.vehicle_id == v.id)).scalar_one_or_none()
        decode = s.get(VinCache, v.vin.upper()) if v.vin else None
    return {
        **_row(v, location),
        "yard": {f: _iso(getattr(v, f)) for f in _YARD_FIELDS if getattr(v, f) not in (None, "")},
        "extras": v.extras or {},
        "match": {
            "resolved": bool(v.car_id_resolved), "method": v.car_id_method, "confidence": v.car_id_confidence,
            "carId": v.car_id, "attemptedAt": _iso(v.resolve_attempted_at),
            "candidates": describe_cars(pi, list(v.car_id_candidates or [])[:50]),
            "candidateCount": len(v.car_id_candidates or []),
        },
        "discrepancy": None if d is None else {
            "reason": d.reason, "status": d.status, "nhtsaYear": d.nhtsa_year, "nhtsaMake": d.nhtsa_make,
            "nhtsaModel": d.nhtsa_model, "nhtsaSeries": d.nhtsa_series,
        },
        "decode": None if decode is None else {
            "error": decode.error_code, "fetchedAt": _iso(decode.fetched_at), "raw": decode.raw or {},
        },
    }


@router.post("/vehicles/{vehicle_id}/rematch")
def rematch(vehicle_id: int, eng=Depends(engines)):
    """Back to the worker's queue, manual choice included; it re-matches within seconds."""
    with Session(eng[0]) as s:
        if s.get(V, vehicle_id) is None:
            raise HTTPException(404, "no such vehicle")
        requeue(s, [vehicle_id], include_matched=True)
        s.commit()
    return {"requeued": vehicle_id}


class ManualMatch(BaseModel):
    car_id: int = Field(ge=1)


@router.post("/vehicles/{vehicle_id}/manual")
def manual(vehicle_id: int, body: ManualMatch, eng=Depends(engines)):
    ji, pi = eng
    car = describe_cars(pi, [body.car_id])[0]
    if car.get("missing"):
        raise HTTPException(422, {"field": "car_id", "message": f"car {body.car_id} is not in the catalogue"})
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    with Session(ji) as s:
        v = s.get(V, vehicle_id)
        if v is None:
            raise HTTPException(404, "no such vehicle")
        v.car_id, v.car_id_candidates, v.car_id_resolved = body.car_id, [body.car_id], True
        v.car_id_method, v.car_id_confidence, v.resolve_attempted_at = "manual", 1.0, now
        s.execute(delete(D).where(D.vehicle_id == vehicle_id))  # matched is matched
        s.commit()
    return {"vehicle": vehicle_id, "car": car}


def _vehicle_source(eng, vehicle_id: int) -> str:
    with Session(eng[0]) as s:
        source = s.execute(select(V.source).where(V.id == vehicle_id)).scalar()
    if source is None:
        raise HTTPException(404, "no such vehicle")
    return source


@router.get("/vehicles/{vehicle_id}/scrapejob")
def scrape_job(vehicle_id: int, eng=Depends(engines)):
    source = _vehicle_source(eng, vehicle_id)
    try:
        cr = scrapejobs.find(source)
    except scrapejobs.Unavailable as exc:
        return {"available": False, "reason": str(exc), "source": source}
    if cr is None:
        return {"available": False, "reason": f"no ScrapeJob for yard {source}", "source": source}
    return {"available": True, "source": source, "job": scrapejobs.summarize(cr)}


@router.post("/vehicles/{vehicle_id}/rescrape")
def rescrape(vehicle_id: int, eng=Depends(engines)):
    source = _vehicle_source(eng, vehicle_id)
    try:
        cr = scrapejobs.find(source)
        if cr is None:
            raise HTTPException(404, f"no ScrapeJob for yard {source}")
        scrapejobs.run_now(cr["metadata"]["name"])
    except scrapejobs.Unavailable as exc:
        raise HTTPException(503, str(exc)) from None
    return {"job": cr["metadata"]["name"], "requested": True}


# ── catalogue cascade for the manual picker ────────────────────────────────────────────────────────

@router.get("/catalogue/years")
def years(eng=Depends(engines)):
    with eng[1].connect() as conn:
        rows = conn.execute(select(pi_year_table.c.name).join(pi_car_table, pi_car_table.c.year_id == pi_year_table.c.id)
                            .distinct()).scalars().all()
    return sorted((int(y) for y in rows if str(y).isdigit()), reverse=True)


@router.get("/catalogue/year-makes")
def year_makes(year: int, eng=Depends(engines)):
    with eng[1].connect() as conn:
        return sorted(conn.execute(
            select(pi_make_table.c.name).join(pi_car_table, pi_car_table.c.make_id == pi_make_table.c.id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .where(pi_year_table.c.name == str(year)).distinct()).scalars().all())


@router.get("/catalogue/year-models")
def year_models(year: int, make: str, eng=Depends(engines)):
    with eng[1].connect() as conn:
        return sorted(conn.execute(
            select(pi_model_table.c.name).join(pi_car_table, pi_car_table.c.model_id == pi_model_table.c.id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id)
            .where(pi_year_table.c.name == str(year), func.lower(pi_make_table.c.name) == make.lower())
            .distinct()).scalars().all())


@router.get("/catalogue/cars")
def cars(year: int, make: str, model: str, eng=Depends(engines)):
    with eng[1].connect() as conn:
        ids = conn.execute(
            select(pi_car_table.c.id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .join(pi_make_table, pi_make_table.c.id == pi_car_table.c.make_id)
            .join(pi_model_table, pi_model_table.c.id == pi_car_table.c.model_id)
            .where(pi_year_table.c.name == str(year), func.lower(pi_make_table.c.name) == make.lower(),
                   pi_model_table.c.name == model)).scalars().all()
    return sorted(describe_cars(eng[1], list(ids)), key=lambda c: (c.get("trim") or "", c.get("engine") or ""))
