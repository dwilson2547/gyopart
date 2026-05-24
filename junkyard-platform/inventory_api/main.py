from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from uszipcode import SearchEngine

from inventory_api.models import SearchResponse
from inventory_api.search import search_inventory

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
    yield
    _engine.dispose()


app = FastAPI(title="Inventory Search API", lifespan=lifespan)


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
