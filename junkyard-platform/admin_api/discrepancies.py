from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import MappingDiscrepancy, Vehicle
from pipeline.pi_schema import pi_make_table, pi_model_table

router = APIRouter(prefix="/admin/discrepancies", tags=["discrepancies"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

VALID_STATUSES = {"unresolved", "pending_rule", "no_match_in_dataset", "ignored"}


def get_grouped_discrepancies(engine: Engine, status: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.execute(
            select(
                Vehicle.source,
                MappingDiscrepancy.raw_make,
                MappingDiscrepancy.raw_model,
                func.count().label("count"),
                func.min(Vehicle.year).label("min_year"),
                func.max(Vehicle.year).label("max_year"),
                func.array_agg(MappingDiscrepancy.vehicle_id).label("vehicle_ids"),
                func.max(MappingDiscrepancy.fuzzy_make_match).label("best_make_match"),
                func.max(MappingDiscrepancy.fuzzy_make_score).label("best_make_score"),
                func.max(MappingDiscrepancy.fuzzy_model_match).label("best_model_match"),
                func.max(MappingDiscrepancy.fuzzy_model_score).label("best_model_score"),
                func.max(MappingDiscrepancy.candidate_car_id).label("candidate_car_id"),
            )
            .join(Vehicle, MappingDiscrepancy.vehicle_id == Vehicle.id)
            .where(MappingDiscrepancy.status == status)
            .group_by(Vehicle.source, MappingDiscrepancy.raw_make, MappingDiscrepancy.raw_model)
            .order_by(func.count().desc())
        ).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        d["vehicle_ids"] = list(d.get("vehicle_ids") or [])
        result.append(d)
    return result


def get_pi_makes(pi_engine: Engine) -> list[str]:
    with pi_engine.connect() as conn:
        rows = conn.execute(select(pi_make_table.c.name).order_by(pi_make_table.c.name)).all()
    return [r[0] for r in rows]


def get_pi_models_all(pi_engine: Engine) -> list[str]:
    with pi_engine.connect() as conn:
        rows = conn.execute(
            select(pi_model_table.c.name).distinct().order_by(pi_model_table.c.name)
        ).all()
    return [r[0] for r in rows]


def get_pi_models_filtered(make: str | None, pi_engine: Engine | None) -> list[str]:
    if pi_engine is None:
        return []
    with pi_engine.connect() as conn:
        if make:
            rows = conn.execute(
                select(pi_model_table.c.name)
                .join(pi_make_table, pi_model_table.c.make_id == pi_make_table.c.id)
                .where(func.lower(pi_make_table.c.name) == func.lower(make))
                .order_by(pi_model_table.c.name)
            ).all()
        else:
            rows = conn.execute(
                select(pi_model_table.c.name).distinct().order_by(pi_model_table.c.name)
            ).all()
    return [r[0] for r in rows]


def ignore_group(engine: Engine, source: str, raw_make: str | None, raw_model: str | None) -> int:
    with Session(engine) as session:
        discrepancies = session.execute(
            select(MappingDiscrepancy)
            .join(Vehicle, MappingDiscrepancy.vehicle_id == Vehicle.id)
            .where(
                Vehicle.source == source,
                MappingDiscrepancy.raw_make == raw_make,
                MappingDiscrepancy.raw_model == raw_model,
                MappingDiscrepancy.status.in_(["unresolved", "no_match_in_dataset"]),
            )
        ).scalars().all()
        for d in discrepancies:
            d.status = "ignored"
        session.commit()
    return len(discrepancies)


def _get_engine() -> Engine:
    from admin_api.main import _engine
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return _engine


def _get_pi_engine() -> Engine | None:
    from admin_api.main import _pi_engine
    return _pi_engine


class _IgnoreRequest(BaseModel):
    source: str
    raw_make: str | None = None
    raw_model: str | None = None


@router.get("")
def list_discrepancies(status: str, engine: Engine = Depends(_get_engine)):
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    groups = get_grouped_discrepancies(engine, status)
    return {"groups": groups, "total": len(groups)}


@router.post("/ignore")
def ignore_discrepancy_group(body: _IgnoreRequest, engine: Engine = Depends(_get_engine)):
    updated = ignore_group(engine, body.source, body.raw_make, body.raw_model)
    return {"updated": updated}


@admin_router.get("/pi-models")
def get_models_endpoint(make: str | None = None, pi_engine: Engine | None = Depends(_get_pi_engine)):
    return {"models": get_pi_models_filtered(make, pi_engine)}
