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
