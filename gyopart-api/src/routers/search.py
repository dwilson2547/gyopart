from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.config import settings
from src.db import DbDep
from src.models import car_parts
from src.schemas import SearchResponse

router = APIRouter(prefix="/v1", tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_junkyards(
    db: DbDep,
    part_id: int = Query(...),
    zip: str = Query(..., min_length=5, max_length=5),
    radius_miles: float = Query(50.0, ge=1.0, le=500.0),
):
    car_ids = db.execute(
        select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    ).scalars().all()

    if not car_ids:
        return SearchResponse(results=[])

    try:
        resp = httpx.get(
            f"{settings.inventory_api_url}/inventory/search",
            params={
                "car_ids": ",".join(str(i) for i in car_ids),
                "zip": zip,
                "radius_miles": radius_miles,
            },
            timeout=settings.inventory_api_timeout,
        )
        resp.raise_for_status()
        return SearchResponse(results=resp.json()["results"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"inventory service unavailable: {exc}")
