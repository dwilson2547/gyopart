import re
from pydantic import BaseModel, field_validator
from src.schemas.vehicle import CarOut


class ImageOut(BaseModel):
    id: int
    name: str | None
    url: str | None
    alt_text: str | None
    bucket_path: str | None
    model_config = {"from_attributes": True}


class PartImageOut(BaseModel):
    image_id: int
    part_image_text: str | None
    image: ImageOut
    model_config = {"from_attributes": True}


class PartOut(BaseModel):
    id: int
    part_number: str
    title: str | None
    description: str | None
    other_names: str | None
    positions: list[str] | None
    applications: str | None
    msrp: float | None
    hazmat: bool | None
    images: list[PartImageOut] = []

    @field_validator("applications", mode="before")
    @classmethod
    def strip_html(cls, v: str | None) -> str | None:
        if not v:
            return v
        return re.sub(r"<[^>]+>", "", v).strip()

    model_config = {"from_attributes": True}


class CompatibleCarOut(CarOut):
    pass
