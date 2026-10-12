from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    fits: bool | None = None  # with ?car_id: whether the part fits that car (diagrams are shared across trims)


class DiagramDetailOut(BaseModel):
    id: int
    category_id: int | None
    sub_category_id: int | None
    image_url: str | None
    image_alt: str | None
    label: str | None = None
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
    vin: str | None = None
    arrival_date: datetime | None = None
    match: Literal["exact", "likely"] = "exact"


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


class CarDetailOut(BaseModel):
    car_id: int
    year_id: int
    year: str
    make_id: int
    make: str
    model_id: int
    model: str
    trim_id: int | None
    trim: str | None
    engine_id: int | None
    engine: str | None


class VinDecoded(BaseModel):
    year: str | None
    make: str | None
    model: str | None
    trim: str | None
    series: str | None
    displacement_l: float | None
    cylinders: int | None
    fuel: str | None
    drive: str | None
    body: str | None
    error_code: str | None
    error_text: str | None


class VinDecodeOut(BaseModel):
    vin: str
    decoded: VinDecoded
    candidates: list[CarDetailOut]
    narrowed_by: list[str]


class TreeSubcategoryOut(BaseModel):
    id: int
    name: str
    label: str
    diagram_count: int


class TreeCategoryOut(BaseModel):
    id: int
    name: str
    label: str
    subcategories: list[TreeSubcategoryOut]


class CarDiagramOut(BaseModel):
    id: int
    category_id: int | None
    sub_category_id: int | None
    image_url: str | None
    label: str | None
    part_count: int
    fitting_part_count: int


class PartHitOut(BaseModel):
    part_id: int
    part_number: str | None
    title: str | None
    matched: Literal["title", "number", "other"]
    diagram_id: int | None
    part_index: str | None
    category_id: int | None
    sub_category_id: int | None


class PartSearchOut(BaseModel):
    q: str
    hits: list[PartHitOut]
    truncated: bool


class ImageSet(BaseModel):
    """One picture; the parts sites store each at three sizes (640/300/150 px wide)."""
    large: str
    medium: str
    small: str
    callout: str | None = None  # for illustrations: the part's reference number on it


class PartDiagramOut(BaseModel):
    diagram_id: int
    image_url: str | None
    label: str | None
    part_index: str | None
    category_id: int | None
    sub_category_id: int | None


class PartDetailOut(BaseModel):
    id: int
    part_number: str | None
    title: str | None
    other_names: list[str]
    description: str | None
    replaces: str | None
    positions: str | None
    notes: str | None
    msrp: float | None
    manufacturer: str | None
    photos: list[ImageSet]
    illustrations: list[ImageSet]
    diagrams: list[PartDiagramOut]
    fit_count: int
    fits_car: bool | None
