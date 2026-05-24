from pydantic import BaseModel


class JunkyardOut(BaseModel):
    id: int
    name: str
    city: str | None
    state: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    website: str | None
    model_config = {"from_attributes": True}


class JunkyardSearchOut(BaseModel):
    junkyard: JunkyardOut
    distance_miles: float | None
    matching_vehicles: list[str]
    inventory_count: int
