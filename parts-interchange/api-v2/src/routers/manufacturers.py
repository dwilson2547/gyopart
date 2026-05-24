from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from src.database import DbDep
from src.models.parts import Manufacturer

router = APIRouter(prefix="/v1/manufacturers", tags=["misc"])


class ManufacturerOut(BaseModel):
    id: int
    name: str
    base_url: str | None
    model_config = {"from_attributes": True}


@router.get("", response_model=list[ManufacturerOut])
async def get_manufacturers(db: DbDep):
    result = await db.execute(select(Manufacturer).order_by(Manufacturer.name))
    return result.scalars().all()
