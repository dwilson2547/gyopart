from pydantic import BaseModel


class YearOut(BaseModel):
    id: int
    name: str
    model_config = {"from_attributes": True}


class MakeOut(BaseModel):
    id: int
    name: str
    select_value: str | None
    start_year: int | None
    end_year: int | None
    model_config = {"from_attributes": True}


class ModelOut(BaseModel):
    id: int
    name: str
    select_value: str | None
    model_config = {"from_attributes": True}


class TrimOut(BaseModel):
    id: int
    name: str
    select_value: str | None
    model_config = {"from_attributes": True}


class EngineOut(BaseModel):
    id: int
    name: str
    select_value: str | None
    model_config = {"from_attributes": True}


class CarOut(BaseModel):
    id: int
    car_id: str | None
    vehicle_id: str | None
    year: YearOut
    make: MakeOut
    model: ModelOut
    trim: TrimOut
    engine: EngineOut
    model_config = {"from_attributes": True}
