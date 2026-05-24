from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from src.db import DbDep
from src.models import Diagram, Image, Part, diagram_parts
from src.schemas import DiagramDetailOut, DiagramPartOut

router = APIRouter(prefix="/v1/diagrams", tags=["diagrams"])


@router.get("/{diagram_id}", response_model=DiagramDetailOut)
def get_diagram(diagram_id: int, db: DbDep):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="diagram not found")

    image = db.get(Image, diagram.image_id) if diagram.image_id else None

    rows = db.execute(
        select(Part, diagram_parts.c.part_index)
        .join(diagram_parts, diagram_parts.c.part_id == Part.id)
        .where(diagram_parts.c.diagram_id == diagram_id)
        .order_by(diagram_parts.c.part_index)
    ).all()

    return DiagramDetailOut(
        id=diagram.id,
        category_id=diagram.category_id,
        sub_category_id=diagram.sub_category_id,
        image_url=image.url if image else None,
        image_alt=image.alt_text if image else None,
        parts=[
            DiagramPartOut(
                part_index=idx,
                id=part.id,
                title=part.title,
                part_number=part.part_number,
                description=part.description,
                other_names=part.other_names,
            )
            for part, idx in rows
        ],
    )
