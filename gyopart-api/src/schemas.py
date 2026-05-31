from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class YearOut(_OrmBase):
    id: int
    name: str


class MakeOut(_OrmBase):
    id: int
    name: str


class ModelOut(_OrmBase):
    id: int
    name: str
    make_id: int


class TrimOut(_OrmBase):
    id: int
    name: str


class EngineOut(_OrmBase):
    id: int
    name: str


class CarOut(_OrmBase):
    id: int
    year_id: int
    make_id: int
    model_id: int
    trim_id: int
    engine_id: int


class PartOut(_OrmBase):
    id: int
    title: str | None
    part_number: str | None
    description: str | None
    other_names: str | None


class CategoryOut(_OrmBase):
    id: int
    name: str


class DiagramOut(_OrmBase):
    id: int
    category_id: int | None
    sub_category_id: int | None
    image_id: int | None
    sub_category_name: str | None = None


class DiagramPartOut(_OrmBase):
    part_index: str | None
    id: int
    title: str | None
    part_number: str | None
    description: str | None
    other_names: str | None


class DiagramDetailOut(BaseModel):
    id: int
    category_id: int | None
    sub_category_id: int | None
    image_url: str | None
    image_alt: str | None
    parts: list[DiagramPartOut]


class PagedPartsResponse(BaseModel):
    items: list[PartOut]
    total: int
    page: int
    per_page: int


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


class YardResult(BaseModel):
    location_id: int
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    distance_miles: float
    lat: float | None = None
    lng: float | None = None
    matching_vehicles: list[VehicleResult]


class SearchResponse(BaseModel):
    results: list[YardResult]
