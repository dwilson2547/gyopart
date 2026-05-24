from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from src.db import DbDep
from src.models import Part, car_parts
from src.schemas import PagedPartsResponse, PartOut

router = APIRouter(prefix="/v1/parts", tags=["parts"])


@router.get("", response_model=PagedPartsResponse)
def get_parts(
    db: DbDep,
    car_id: int = Query(...),
    filter: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    q = (
        select(Part)
        .join(car_parts, car_parts.c.part_id == Part.id)
        .where(car_parts.c.car_id == car_id)
    )
    if filter:
        q = q.where(Part.title.icontains(filter) | Part.part_number.icontains(filter))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    items = (
        db.execute(
            q.order_by(Part.part_number.asc().nulls_last(), Part.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .scalars()
        .all()
    )
    return PagedPartsResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{part_id}", response_model=PartOut)
def get_part(part_id: int, db: DbDep):
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="part not found")
    return part


@router.get("/{part_id}/compatible-cars", response_model=list[int])
def get_compatible_car_ids(part_id: int, db: DbDep):
    return db.execute(
        select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    ).scalars().all()
