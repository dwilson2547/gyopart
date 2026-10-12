from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from src.db import DbDep
from src.models import Car, Diagram, Engine, Image, Make, Manufacturer, Model, Part, Trim, Year, Subcategory, car_diagrams, car_parts, diagram_parts, part_images
from src.routers.catalogue import best_label, label_from_alt
from src.schemas import (
    ImageSet, InterchangeCar, InterchangeMake, InterchangeModel, InterchangeOut, InterchangeYear,
    PagedPartsResponse, PartDetailOut, PartDiagramOut, PartLookupOut, PartNumberHit, PartOut,
)

_REF_RE = re.compile(r"reference\s*#\s*(\w+)", re.IGNORECASE)
MAX_DIAGRAMS = 6


def image_sets(rows: list[tuple[str, str | None]]) -> list[ImageSet]:
    """Group id-ordered (url, text) rows into pictures. The sites store each picture three times, large →
    medium → small, in consecutive rows; when a set doesn't divide by three, every row is its own picture."""
    def callout(text):
        m = _REF_RE.search(text or "")
        return m.group(1) if m else None
    if rows and len(rows) % 3 == 0:
        return [ImageSet(large=rows[i][0], medium=rows[i + 1][0], small=rows[i + 2][0], callout=callout(rows[i][1]))
                for i in range(0, len(rows), 3)]
    return [ImageSet(large=u, medium=u, small=u, callout=callout(t)) for u, t in rows]

router = APIRouter(prefix="/v1/parts", tags=["parts"])


@router.get("", response_model=PagedPartsResponse)
def get_parts(
    db: DbDep,
    car_id: int = Query(...),
    filter: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    q = (
        select(Part)
        .join(car_parts, car_parts.c.part_id == Part.id)
        .where(car_parts.c.car_id == car_id)
    )
    if filter:
        q = q.where(Part.title.icontains(filter) | Part.part_number.icontains(filter))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    items = (
        db.execute(
            q.order_by(Part.part_number.asc().nulls_last(), Part.id)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .scalars()
        .all()
    )
    return PagedPartsResponse(items=items, total=total, page=page, per_page=per_page)


LOOKUP_LIMIT = 20


def normalize_number(q: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", q).upper()


# Declared before /{part_id} so "lookup" isn't taken for a part id.
@router.get("/lookup", response_model=PartLookupOut)
def lookup_part_number(db: DbDep, q: str = Query(..., min_length=1, max_length=60)):
    """Part numbers matching q, ignoring dashes, spaces and case. There's no index on the normalized number, so
    candidates are narrowed with the part_number trigram index on the first three characters (as stored, or
    after a leading dash, like Ford's "-W715092-S437") and then compared normalized."""
    n = normalize_number(q)
    if len(n) < 3:
        raise HTTPException(status_code=422, detail="Type at least 3 letters or digits of the part number")
    pre = n[:3]
    normalized = func.upper(func.regexp_replace(Part.part_number, "[^A-Za-z0-9]", "", "g"))
    rows = db.execute(
        select(Part.id, Part.part_number, Part.title, Manufacturer.name.label("manufacturer"),
               (normalized == n).label("exact"))
        .outerjoin(Manufacturer, Manufacturer.id == Part.manufacturer_id)
        .where(or_(Part.part_number.ilike(f"{pre}%"), Part.part_number.ilike(f"-{pre}%")), normalized.like(f"{n}%"))
        .order_by(normalized != n, func.length(Part.part_number), Part.part_number, Manufacturer.name)
        .limit(LOOKUP_LIMIT)
    ).all()
    hit = lambda r: PartNumberHit(id=r.id, part_number=r.part_number, title=r.title, manufacturer=r.manufacturer)
    return PartLookupOut(q=n, exact=[hit(r) for r in rows if r.exact], suggestions=[hit(r) for r in rows if not r.exact])


@router.get("/{part_id}", response_model=PartOut)
def get_part(part_id: int, db: DbDep):
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="part not found")
    return part


@router.get("/{part_id}/compatible-cars", response_model=list[int])
def get_compatible_car_ids(part_id: int, db: DbDep):
    return db.execute(
        select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    ).scalars().all()


@router.get("/{part_id}/detail", response_model=PartDetailOut)
def get_part_detail(part_id: int, db: DbDep, car_id: int | None = Query(None)):
    """Everything the confirm-the-part page shows: identity, pictures, the diagrams it's on (this car's when
    car_id is given, else up to six distinct ones), and how many cars it fits."""
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="part not found")
    manufacturer = db.get(Manufacturer, part.manufacturer_id) if part.manufacturer_id else None

    pics = db.execute(
        select(Image.url, part_images.c.part_image_text)
        .join(part_images, part_images.c.image_id == Image.id)
        .where(part_images.c.part_id == part_id, Image.url.is_not(None))
        .order_by(Image.id)
    ).all()
    photos = image_sets([(u, t) for u, t in pics if not t])
    illustrations = image_sets([(u, t) for u, t in pics if t])

    # diagram_parts has no part_id index (PK is diagram_id, part_id), so reach the diagrams through the cars the
    # part fits: car_parts(part_id) → car_diagrams(car_id, …) → diagram_parts PK. A full scan takes ~8 s.
    cars = select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    if car_id is not None:
        cars = cars.where(car_parts.c.car_id == car_id)
    q = (
        select(Diagram.id, Image.url, Image.alt_text, Subcategory.name.label("sname"), diagram_parts.c.part_index,
               Diagram.category_id, Diagram.sub_category_id)
        .select_from(car_diagrams)
        .join(diagram_parts, (diagram_parts.c.diagram_id == car_diagrams.c.diagram_id)
              & (diagram_parts.c.part_id == part_id))
        .join(Diagram, Diagram.id == car_diagrams.c.diagram_id)
        .outerjoin(Image, Image.id == Diagram.image_id)
        .outerjoin(Subcategory, Subcategory.id == Diagram.sub_category_id)
        .where(car_diagrams.c.car_id.in_(cars.scalar_subquery()))
        .distinct()
        .order_by(Diagram.id)
        .limit(500)
    )
    rows = db.execute(q).all()
    diagrams: list[PartDiagramOut] = []
    seen: set[str | None] = set()
    for r in rows:
        if r.url in seen:  # the same drawing is shared by many cars' diagrams
            continue
        seen.add(r.url)
        diagrams.append(PartDiagramOut(
            diagram_id=r.id, image_url=r.url, part_index=r.part_index, category_id=r.category_id,
            sub_category_id=r.sub_category_id,
            label=best_label([r.alt_text], r.sname) if r.sname else label_from_alt(r.alt_text)))
        if len(diagrams) == MAX_DIAGRAMS:
            break

    fit_count = db.execute(select(func.count()).select_from(car_parts).where(car_parts.c.part_id == part_id)).scalar_one()
    fits_car = None
    if car_id is not None:
        fits_car = db.execute(select(car_parts.c.car_id).where(
            car_parts.c.part_id == part_id, car_parts.c.car_id == car_id)).first() is not None

    names = [n.strip() for n in (part.other_names or "").split(",") if n.strip()]
    return PartDetailOut(
        id=part.id, part_number=part.part_number, title=part.title, other_names=names,
        description=part.description, replaces=part.replaces, positions=part.positions, notes=part.notes,
        msrp=part.msrp, manufacturer=manufacturer.name if manufacturer else None,
        photos=photos, illustrations=illustrations, diagrams=diagrams, fit_count=fit_count, fits_car=fits_car,
    )


def year_ranges(years: list[int]) -> str:
    """[2009, 2010, 2011, 2013] → "2009–2011, 2013"."""
    out: list[str] = []
    ys = sorted(set(years))
    i = 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] == ys[j] + 1:
            j += 1
        out.append(str(ys[i]) if i == j else f"{ys[i]}–{ys[j]}")
        i = j + 1
    return ", ".join(out)


def group_interchange(part_id: int, rows) -> InterchangeOut:
    """Rows of (car_id, year, make, model, trim, engine) → make → model → year → cars."""
    tree: dict[str, dict[str, dict[int, list[InterchangeCar]]]] = {}
    for r in rows:
        try:
            year = int(r.year)
        except (TypeError, ValueError):
            continue
        tree.setdefault(r.make, {}).setdefault(r.model, {}).setdefault(year, []).append(
            InterchangeCar(car_id=r.car_id, trim=r.trim, engine=r.engine))
    makes = []
    for make in sorted(tree, key=str.lower):
        models = []
        for model in sorted(tree[make], key=str.lower):
            by_year = tree[make][model]
            years = [InterchangeYear(year=y, cars=sorted(by_year[y], key=lambda c: ((c.trim or ""), (c.engine or ""))))
                     for y in sorted(by_year, reverse=True)]
            models.append(InterchangeModel(model=model, year_ranges=year_ranges(list(by_year)),
                                           car_count=sum(len(y.cars) for y in years), years=years))
        makes.append(InterchangeMake(make=make, car_count=sum(m.car_count for m in models), models=models))
    return InterchangeOut(part_id=part_id, car_count=sum(m.car_count for m in makes), makes=makes)


@router.get("/{part_id}/interchange", response_model=InterchangeOut)
def get_interchange(part_id: int, db: DbDep):
    """Every catalogue car this part fits, grouped make → model → year."""
    if db.get(Part, part_id) is None:
        raise HTTPException(status_code=404, detail="part not found")
    rows = db.execute(
        select(Car.id.label("car_id"), Year.name.label("year"), Make.name.label("make"), Model.name.label("model"),
               Trim.name.label("trim"), Engine.name.label("engine"))
        .join(car_parts, (car_parts.c.car_id == Car.id) & (car_parts.c.part_id == part_id))
        .join(Year, Year.id == Car.year_id)
        .join(Make, Make.id == Car.make_id)
        .join(Model, Model.id == Car.model_id)
        .outerjoin(Trim, Trim.id == Car.trim_id)
        .outerjoin(Engine, Engine.id == Car.engine_id)
    ).all()
    return group_interchange(part_id, rows)
