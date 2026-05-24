import math
from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select
from src.database import DbDep
from src.models.junkyard import Junkyard, JunkyardInventory
from src.models.vehicle import Car, Make, Model, Year, car_parts
from src.schemas.common import PagedResponse
from src.schemas.junkyard import JunkyardOut, JunkyardSearchOut
from src.services.geo import haversine_miles

router = APIRouter(prefix="/v1/junkyards", tags=["junkyards"])


@router.get("", response_model=PagedResponse[JunkyardSearchOut])
async def search_junkyards(
    db: DbDep,
    part_id: int = Query(...),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    radius_miles: float | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    compat_q = (
        select(Year.name, Make.name, Model.name)
        .join(Car, Car.year_id == Year.id)
        .join(Make, Car.make_id == Make.id)
        .join(Model, Car.model_id == Model.id)
        .join(car_parts, car_parts.c.car_id == Car.id)
        .where(car_parts.c.part_id == part_id)
        .distinct()
    )
    compat_result = await db.execute(compat_q)
    compatible = compat_result.all()

    if not compatible:
        return PagedResponse(items=[], total=0, page=page, per_page=per_page, pages=0, has_next=False, has_prev=False)

    conditions = or_(*[
        and_(
            JunkyardInventory.year == yr,
            func.lower(func.trim(JunkyardInventory.make_name)) == func.lower(func.trim(mk)),
            func.lower(func.trim(JunkyardInventory.model_name)) == func.lower(func.trim(mdl)),
        )
        for yr, mk, mdl in compatible
    ])

    inv_q = (
        select(Junkyard, func.count(JunkyardInventory.id).label("inv_count"))
        .join(JunkyardInventory, JunkyardInventory.junkyard_id == Junkyard.id)
        .where(JunkyardInventory.date_removed.is_(None))
        .where(conditions)
        .where(Junkyard.active == True)
        .group_by(Junkyard.id)
    )
    rows = (await db.execute(inv_q)).all()

    items = []
    for junkyard, inv_count in rows:
        distance = None
        if lat is not None and lng is not None and junkyard.lat and junkyard.lng:
            distance = haversine_miles(lat, lng, junkyard.lat, junkyard.lng)
            if radius_miles is not None and distance > radius_miles:
                continue
        items.append(JunkyardSearchOut(
            junkyard=JunkyardOut.model_validate(junkyard),
            distance_miles=distance,
            matching_vehicles=[f"{yr} {mk} {mdl}" for yr, mk, mdl in compatible],
            inventory_count=inv_count,
        ))

    if lat is not None and lng is not None:
        items.sort(key=lambda x: x.distance_miles or float("inf"))
    else:
        items.sort(key=lambda x: x.inventory_count, reverse=True)

    total = len(items)
    pages = math.ceil(total / per_page) if per_page else 1
    start = (page - 1) * per_page
    return PagedResponse(items=items[start:start + per_page], total=total, page=page, per_page=per_page, pages=pages, has_next=page < pages, has_prev=page > 1)
