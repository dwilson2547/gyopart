from __future__ import annotations
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VehicleResult(BaseModel):
    vehicle_id: int
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    row: str | None
    car_id: int | None
    color: str | None = None
    mileage: int | None = None
    vin: str | None = None
    arrival_date: datetime | None = None
    match: Literal["exact", "likely"] = "exact"


class LocationResult(BaseModel):
    location_id: int
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    distance_miles: float = Field(ge=0)
    lat: float | None = None
    lng: float | None = None
    matching_vehicles: list[VehicleResult]


class SearchResponse(BaseModel):
    results: list[LocationResult]


class YardOut(BaseModel):
    location_id: int
    name: str
    chain: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    lat: float | None = None
    lng: float | None = None
    last_seen_at: datetime | None = None   # last time a scrape saw the yard
    distance_miles: float | None = None
    vehicle_count: int = 0
    new_this_week: int = 0
    catalogued_count: int = 0              # vehicles matched to at least one catalogue car


class YardModelFacet(BaseModel):
    model: str
    count: int


class YardMakeFacet(BaseModel):
    make: str
    count: int
    models: list[YardModelFacet]


class YardFacets(BaseModel):
    makes: list[YardMakeFacet]
    year_min: int | None
    year_max: int | None


class YardVehicle(BaseModel):
    vehicle_id: int
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    row: str | None
    color: str | None
    vin: str | None
    arrival_date: datetime | None
    car_id: int | None
    car_id_candidates: list[int]


class YardVehiclesPage(BaseModel):
    total: int
    limit: int
    offset: int
    vehicles: list[YardVehicle]
