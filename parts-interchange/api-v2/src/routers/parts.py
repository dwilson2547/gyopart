import math
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from src.database import DbDep
from src.models.parts import Part
from src.models.vehicle import Car, car_parts
from src.schemas.common import PagedResponse
from src.schemas.parts import CompatibleCarOut, PartOut

router = APIRouter(prefix="/v1/parts", tags=["parts"])


@router.get("", response_model=PagedResponse[PartOut])
async def get_parts(
    db: DbDep,
    car_id: int = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    filter: str | None = Query(None),
    sort: str | None = Query(None),
):
    q = select(Part).join(car_parts, car_parts.c.part_id == Part.id).where(car_parts.c.car_id == car_id)
    if filter:
        q = q.where(Part.title.icontains(filter) | Part.part_number.icontains(filter) | Part.other_names.icontains(filter))
    if sort == "title":
        q = q.order_by(Part.title)
    elif sort == "-title":
        q = q.order_by(Part.title.desc())
    else:
        q = q.order_by(Part.part_number.desc())

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    items = result.scalars().all()
    pages = math.ceil(total / per_page) if per_page else 1
    return PagedResponse(items=items, total=total, page=page, per_page=per_page, pages=pages, has_next=page < pages, has_prev=page > 1)


@router.get("/{part_id}", response_model=PartOut)
async def get_part(part_id: int, db: DbDep):
    result = await db.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.get("/{part_id}/compatible-cars", response_model=PagedResponse[CompatibleCarOut])
async def get_compatible_cars(
    part_id: int,
    db: DbDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    q = select(Car).join(car_parts, car_parts.c.car_id == Car.id).where(car_parts.c.part_id == part_id)
    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()
    result = await db.execute(q.offset((page - 1) * per_page).limit(per_page))
    items = result.scalars().all()
    pages = math.ceil(total / per_page) if per_page else 1
    return PagedResponse(items=items, total=total, page=page, per_page=per_page, pages=pages, has_next=page < pages, has_prev=page > 1)
