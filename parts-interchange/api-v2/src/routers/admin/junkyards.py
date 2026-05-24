from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.database import DbDep
from src.middleware.auth import require_admin_key
from src.models.junkyard import Junkyard
from src.schemas.admin import JunkyardIn
from src.schemas.junkyard import JunkyardOut

router = APIRouter(prefix="/v1/admin/junkyards", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("", response_model=list[JunkyardOut])
async def list_junkyards(db: DbDep):
    result = await db.execute(select(Junkyard).order_by(Junkyard.name))
    return result.scalars().all()


@router.post("", response_model=JunkyardOut, status_code=201)
async def create_junkyard(payload: JunkyardIn, db: DbDep):
    jy = Junkyard(**payload.model_dump())
    db.add(jy)
    await db.commit()
    await db.refresh(jy)
    return jy


@router.put("/{junkyard_id}", response_model=JunkyardOut)
async def update_junkyard(junkyard_id: int, payload: JunkyardIn, db: DbDep):
    result = await db.execute(select(Junkyard).where(Junkyard.id == junkyard_id))
    jy = result.scalar_one_or_none()
    if not jy:
        raise HTTPException(status_code=404, detail="Junkyard not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(jy, k, v)
    await db.commit()
    await db.refresh(jy)
    return jy


@router.delete("/{junkyard_id}", status_code=204)
async def delete_junkyard(junkyard_id: int, db: DbDep):
    result = await db.execute(select(Junkyard).where(Junkyard.id == junkyard_id))
    jy = result.scalar_one_or_none()
    if not jy:
        raise HTTPException(status_code=404, detail="Junkyard not found")
    await db.delete(jy)
    await db.commit()
