"""
A car's catalogue for browsing: category → subcategory tree, a subcategory's diagrams, and part search that
says where each hit sits in the tree.

Category and subcategory names are slugs ("belts-and-cooling"). The diagram images' alt text carries the site's
display name ("Cooling Fan, Clutch & Motor for 2011 Ford F-150 #0"), so subcategory and diagram labels come
from there, falling back to a prettified slug.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, or_, select

from src.db import DbDep
from src.models import (
    Car, Category, Diagram, Image, Part, Subcategory, car_diagrams, car_parts, diagram_parts,
)
from src.schemas import (
    CarDiagramOut, PartHitOut, PartSearchOut, TreeCategoryOut, TreeSubcategoryOut,
)

router = APIRouter(prefix="/v1/cars", tags=["catalogue"])

_ALT_RE = re.compile(r"^(.*?) for \d{4} .*?(?: #\d+)?$")
_SMALL = {"and", "or", "of", "the", "a", "an", "in", "on", "to", "for", "with"}
SEARCH_LIMIT = 300


def pretty(slug: str | None) -> str:
    words = (slug or "").replace("_", "-").split("-")
    return " ".join(w if i and w in _SMALL else w.capitalize() for i, w in enumerate(words) if w)


def label_from_alt(alt: str | None, slug: str | None = None) -> str | None:
    """Display name from an image alt text; with `slug`, only when it is that slug's name (some diagrams carry
    another subcategory's alt text, e.g. a back-panel diagram labelled "Aperture Panel")."""
    m = _ALT_RE.match((alt or "").strip())
    if not m:
        return None
    label = m.group(1).strip()
    if slug is not None and _key(label) != _key(slug):
        return None
    return label


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("&", "and"))


def best_label(alts, slug: str) -> str:
    for alt in alts or []:
        label = label_from_alt(alt, slug)
        if label:
            return label
    return pretty(slug)


def _require_car(db, car_id: int) -> None:
    if db.get(Car, car_id) is None:
        raise HTTPException(status_code=404, detail="car not found")


@router.get("/{car_id}/tree", response_model=list[TreeCategoryOut])
def get_tree(car_id: int, db: DbDep):
    """Every category → subcategory with diagrams for this car, with diagram counts."""
    _require_car(db, car_id)
    rows = db.execute(
        select(
            Category.id.label("cid"), Category.name.label("cname"),
            Subcategory.id.label("sid"), Subcategory.name.label("sname"),
            func.count(Diagram.id).label("n"), func.array_agg(Image.alt_text.distinct()).label("alts"),
        )
        .select_from(car_diagrams)
        .join(Diagram, Diagram.id == car_diagrams.c.diagram_id)
        .join(Category, Category.id == Diagram.category_id)
        .join(Subcategory, Subcategory.id == Diagram.sub_category_id)
        .outerjoin(Image, Image.id == Diagram.image_id)
        .where(car_diagrams.c.car_id == car_id)
        .group_by(Category.id, Category.name, Subcategory.id, Subcategory.name)
    ).all()

    tree: dict[int, TreeCategoryOut] = {}
    for r in rows:
        cat = tree.setdefault(r.cid, TreeCategoryOut(id=r.cid, name=r.cname, label=pretty(r.cname), subcategories=[]))
        cat.subcategories.append(TreeSubcategoryOut(
            id=r.sid, name=r.sname, label=best_label(r.alts, r.sname), diagram_count=r.n))
    for cat in tree.values():
        cat.subcategories.sort(key=lambda s: s.label.lower())
    return sorted(tree.values(), key=lambda c: c.label.lower())


@router.get("/{car_id}/diagrams", response_model=list[CarDiagramOut])
def get_car_diagrams(car_id: int, db: DbDep, sub_category_id: int = Query(...)):
    """A subcategory's diagrams for this car, with how many of each diagram's parts fit the car."""
    _require_car(db, car_id)
    fits = (
        select(func.count())
        .select_from(diagram_parts)
        .join(car_parts, (car_parts.c.part_id == diagram_parts.c.part_id) & (car_parts.c.car_id == car_id))
        .where(diagram_parts.c.diagram_id == Diagram.id)
        .scalar_subquery()
    )
    total = (
        select(func.count()).select_from(diagram_parts).where(diagram_parts.c.diagram_id == Diagram.id)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Diagram.id, Diagram.category_id, Diagram.sub_category_id, Image.url, Image.alt_text,
               Subcategory.name.label("sname"), fits.label("fits"), total.label("total"))
        .join(car_diagrams, (car_diagrams.c.diagram_id == Diagram.id) & (car_diagrams.c.car_id == car_id))
        .outerjoin(Image, Image.id == Diagram.image_id)
        .outerjoin(Subcategory, Subcategory.id == Diagram.sub_category_id)
        .where(Diagram.sub_category_id == sub_category_id)
        .order_by(Diagram.id)
    ).all()
    return [
        CarDiagramOut(id=r.id, category_id=r.category_id, sub_category_id=r.sub_category_id, image_url=r.url,
                      label=best_label([r.alt_text], r.sname) if r.sname else label_from_alt(r.alt_text), part_count=r.total, fitting_part_count=r.fits)
        for r in rows
    ]


@router.get("/{car_id}/parts/search", response_model=PartSearchOut)
def search_car_parts(car_id: int, db: DbDep, q: str = Query(..., min_length=2, max_length=100)):
    """Parts fitting this car whose name, number or other names match, each placed on its diagram(s).
    Title matches rank first, then part numbers, then other names."""
    _require_car(db, car_id)
    term = q.strip()
    like = f"%{term}%"
    number_like = f"%{re.sub(r'[^A-Za-z0-9]', '', term)}%"
    number_hit = func.regexp_replace(Part.part_number, "[^A-Za-z0-9]", "", "g").ilike(number_like)
    matched = case(
        (Part.title.ilike(like), "title"),
        (number_hit, "number"),
        else_="other",
    )
    rank = case((Part.title.ilike(like), 0), (number_hit, 1), else_=2)
    on_diagram = (
        select(diagram_parts.c.part_id, diagram_parts.c.diagram_id, diagram_parts.c.part_index,
               Diagram.category_id, Diagram.sub_category_id)
        .join(car_diagrams, (car_diagrams.c.diagram_id == diagram_parts.c.diagram_id)
              & (car_diagrams.c.car_id == car_id))
        .join(Diagram, Diagram.id == diagram_parts.c.diagram_id)
        .subquery()
    )
    rows = db.execute(
        select(Part.id, Part.part_number, Part.title, Part.category_id.label("part_category_id"), matched.label("m"),
               on_diagram.c.diagram_id, on_diagram.c.part_index, on_diagram.c.category_id,
               on_diagram.c.sub_category_id)
        .join(car_parts, (car_parts.c.part_id == Part.id) & (car_parts.c.car_id == car_id))
        .outerjoin(on_diagram, on_diagram.c.part_id == Part.id)
        .where(or_(Part.title.ilike(like), number_hit, Part.other_names.ilike(like)))
        .order_by(rank, Part.title, Part.id)
        .limit(SEARCH_LIMIT + 1)
    ).all()
    hits = [
        PartHitOut(part_id=r.id, part_number=r.part_number, title=r.title, matched=r.m,
                   diagram_id=r.diagram_id, part_index=r.part_index,
                   category_id=r.category_id if r.diagram_id else r.part_category_id,
                   sub_category_id=r.sub_category_id)
        for r in rows[:SEARCH_LIMIT]
    ]
    return PartSearchOut(q=term, hits=hits, truncated=len(rows) > SEARCH_LIMIT)
