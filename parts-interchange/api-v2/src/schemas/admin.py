import datetime
from pydantic import BaseModel


class JunkyardIn(BaseModel):
    name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    lat: float | None = None
    lng: float | None = None
    phone: str | None = None
    website: str | None = None
    active: bool = True


class ScrapeConfigIn(BaseModel):
    junkyard_id: int | None = None
    site_type: str
    url: str
    scrape_interval_hours: int = 24
    enabled: bool = True


class ScrapeJobOut(BaseModel):
    id: int
    scrape_site_config_id: int | None
    status: str
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    error_message: str | None
    model_config = {"from_attributes": True}
