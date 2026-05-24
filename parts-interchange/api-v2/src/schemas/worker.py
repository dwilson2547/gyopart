from pydantic import BaseModel


class JobStatusIn(BaseModel):
    status: str
    error_message: str | None = None


class PartBatchIn(BaseModel):
    class PartItem(BaseModel):
        part_number: str
        title: str | None = None
        url: str | None = None
        manufacturer_id: int
        other_names: str | None = None
        description: str | None = None
        positions: list[str] | None = None
        msrp: float | None = None
        applications: str | None = None
        hazmat: bool | None = None

    parts: list[PartItem]
    job_id: int


class ImageBatchIn(BaseModel):
    class ImageItem(BaseModel):
        name: str
        url: str | None = None
        alt_text: str | None = None
        bucket_path: str | None = None
        manufacturer_id: int

    images: list[ImageItem]
    job_id: int


class CarBatchIn(BaseModel):
    class CarItem(BaseModel):
        year: str
        make_select_value: str
        make_ui: str
        model_select_value: str
        model_ui: str
        trim_select_value: str
        trim_ui: str
        engine_select_value: str
        engine_ui: str
        manufacturer_id: int
        car_id: str | None = None
        vehicle_id: str | None = None
        base_url: str | None = None
        part_numbers: list[str] = []

    cars: list[CarItem]
    job_id: int
