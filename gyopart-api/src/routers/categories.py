from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.db import DbDep
from src.models import Category, Subcategory, Diagram, car_diagrams
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
    diagrams = db.execute(
        select(Diagram)
        .where(Diagram.category_id == category_id, Diagram.id.in_(car_diagram_ids))
        .order_by(Diagram.id)
    ).scalars().all()

    sub_ids = {d.sub_category_id for d in diagrams if d.sub_category_id}
    subcats: dict[int, str] = {}
    if sub_ids:
        subcats = {
            s.id: s.name
            for s in db.execute(
                select(Subcategory).where(Subcategory.id.in_(sub_ids))
            ).scalars().all()
        }

    return [
        DiagramOut(
            id=d.id,
            category_id=d.category_id,
            sub_category_id=d.sub_category_id,
            image_id=d.image_id,
            sub_category_name=subcats.get(d.sub_category_id) if d.sub_category_id else None,
        )
        for d in diagrams
    ]
