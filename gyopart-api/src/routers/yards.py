"""Yard browsing, proxied from inventory-api. Vehicles come back with their catalogue candidates named (year,
make, model, trim, engine) so the UI can link a yard car to its parts catalogue and add it to the garage."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from src.config import settings
from src.db import DbDep
from src.models import Car
from src.routers.cars import _car_query
from src.schemas import CarDetailOut, YardFacetsOut, YardOut, YardVehiclesOut

router = APIRouter(prefix="/v1/yards", tags=["yards"])


def _inventory(path: str, params: dict | None = None):
    try:
        resp = httpx.get(f"{settings.inventory_api_url.rstrip('/')}{path}",
                         params={k: v for k, v in (params or {}).items() if v is not None},
                         timeout=settings.inventory_api_timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"inventory service unavailable: {exc}")
    if resp.status_code in (404, 422):
        raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail", "not found"))
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"inventory service error ({resp.status_code})")
    return resp.json()


@router.get("", response_model=list[YardOut])
def list_yards(zip: str | None = Query(None, min_length=5, max_length=5)):
    return _inventory("/inventory/locations", {"zip": zip})


@router.get("/{location_id}", response_model=YardOut)
def get_yard(location_id: int):
    return _inventory(f"/inventory/locations/{location_id}")


@router.get("/{location_id}/facets", response_model=YardFacetsOut)
def get_yard_facets(location_id: int):
    return _inventory(f"/inventory/locations/{location_id}/facets")


@router.get("/{location_id}/vehicles", response_model=YardVehiclesOut)
def get_yard_vehicles(
    location_id: int,
    db: DbDep,
    make: str | None = Query(None),
    model: str | None = Query(None),
    year: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    page = _inventory(f"/inventory/locations/{location_id}/vehicles",
                      {"make": make, "model": model, "year": year, "limit": limit, "offset": offset})
    ids = {c for v in page["vehicles"] for c in v.get("car_id_candidates") or []}
    names: dict[int, dict] = {}
    if ids:
        names = {r["car_id"]: dict(r) for r in db.execute(_car_query().where(Car.id.in_(ids))).mappings().all()}
    for v in page["vehicles"]:
        v["candidates"] = [CarDetailOut(**names[c]) for c in v.get("car_id_candidates") or [] if c in names]
    return page
