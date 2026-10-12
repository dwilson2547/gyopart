from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from uszipcode import SearchEngine

from junkyard_common.models import Base
from inventory_api.models import SearchResponse, YardFacets, YardOut, YardVehiclesPage
from inventory_api.search import search_inventory
from inventory_api import yards

_engine: Engine | None = None

_ZIP_RE = re.compile(r"^\d{5}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=5000"},
    )
    Base.metadata.create_all(_engine)
    yield
    _engine.dispose()


app = FastAPI(title="Inventory Search API", version="3.0.2", lifespan=lifespan)


def _parse_car_ids(raw: str) -> list[int]:
    try:
        ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="car_ids must be comma-separated integers")
    if not ids:
        raise HTTPException(status_code=422, detail="car_ids must contain at least 1 value")
    if len(ids) > 100:
        raise HTTPException(status_code=422, detail="car_ids must contain at most 100 values")
    return ids


def _resolve_zip(zip_code: str) -> tuple[float, float]:
    if not _ZIP_RE.match(zip_code):
        raise HTTPException(status_code=422, detail="zip must be a 5-digit string")
    with SearchEngine() as se:
        result = se.by_zipcode(zip_code)
    if not result or result.lat is None or result.lng is None:
        raise HTTPException(status_code=422, detail="zip code not found")
    return result.lat, result.lng


@app.get("/inventory/search", response_model=SearchResponse)
def search(
    car_ids: str = Query(..., description="Comma-separated list of car IDs"),
    zip: str = Query(..., description="5-digit US zip code"),
    radius_miles: float = Query(50.0, ge=1.0, le=500.0, description="Search radius in miles"),
):
    ids = _parse_car_ids(car_ids)
    lat, lng = _resolve_zip(zip)
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    results = search_inventory(_engine, ids, lat, lng, radius_miles)
    return SearchResponse(results=results)


class SearchRequest(BaseModel):
    # A part's interchange can span thousands of catalogue cars, more than fits a query string.
    car_ids: list[int] = Field(..., min_length=1, max_length=50000)
    zip: str
    radius_miles: float = Field(50.0, ge=1.0, le=500.0)


@app.post("/inventory/search", response_model=SearchResponse)
def search_post(body: SearchRequest):
    lat, lng = _resolve_zip(body.zip)
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return SearchResponse(results=search_inventory(_engine, body.car_ids, lat, lng, body.radius_miles))


def _engine_or_503() -> Engine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return _engine


@app.get("/inventory/locations", response_model=list[YardOut])
def locations(zip: str | None = Query(None, description="5-digit ZIP: adds distance and sorts nearest first")):
    lat, lng = _resolve_zip(zip) if zip else (None, None)
    return yards.list_yards(_engine_or_503(), lat, lng)


@app.get("/inventory/locations/{location_id}", response_model=YardOut)
def location(location_id: int):
    yard = yards.get_yard(_engine_or_503(), location_id)
    if yard is None:
        raise HTTPException(status_code=404, detail="yard not found")
    return yard


@app.get("/inventory/locations/{location_id}/facets", response_model=YardFacets)
def location_facets(location_id: int):
    return yards.yard_facets(_engine_or_503(), location_id)


@app.get("/inventory/locations/{location_id}/vehicles", response_model=YardVehiclesPage)
def location_vehicles(
    location_id: int,
    make: str | None = Query(None),
    model: str | None = Query(None),
    year: int | None = Query(None, ge=1900, le=2100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return yards.yard_vehicles(_engine_or_503(), location_id, make, model, year, limit, offset)
