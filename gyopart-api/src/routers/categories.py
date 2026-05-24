from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.db import DbDep
from src.models import Category, Diagram, car_diagrams
from src.schemas import CategoryOut, DiagramOut

router = APIRouter(prefix="/v1/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def get_categories(db: DbDep, car_id: int = Query(...)):
    car_diagram_ids = select(car_diagrams.c.diagram_id).where(car_diagrams.c.car_id == car_id)
    category_ids = select(Diagram.category_id).where(Diagram.id.in_(car_diagram_ids)).distinct()
    return db.execute(
        select(Category).where(Category.id.in_(category_ids)).order_by(Category.name)
    ).scalars().all()


@router.get("/{category_id}/diagrams", response_model=list[DiagramOut])
def get_diagrams(category_id: int, db: DbDep, car_id: int = Query(...)):
    if db.get(Category, category_id) is None:
        raise HTTPException(status_code=404, detail="category not found")
    car_diagram_ids = select(car_diagrams.c.diagram_id).where(car_diagrams.c.car_id == car_id)
    return db.execute(
        select(Diagram)
        .where(Diagram.category_id == category_id, Diagram.id.in_(car_diagram_ids))
        .order_by(Diagram.id)
    ).scalars().all()
