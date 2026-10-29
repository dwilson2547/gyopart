"""Catalogue lookups for the pickers: makes, models of a make with the years they exist, and the
suggestions shown on a discrepancy group. Targets are only ever chosen from these lists."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from pipeline.car_matcher import name_key
from pipeline.pi_schema import pi_car_table, pi_make_table, pi_model_table, pi_trim_table, pi_year_table

from .common import engines

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])

_YEAR = func.cast(pi_year_table.c.name, pi_car_table.c.id.type)


def catalogue_make(pi: Engine, name: str | None) -> str | None:
    """The catalogue's spelling of a make (NHTSA says MERCEDES-BENZ, the catalogue Mercedes-Benz)."""
    if not name:
        return None
    with pi.connect() as conn:
        return conn.execute(select(pi_make_table.c.name)
                            .where(func.lower(pi_make_table.c.name) == name.strip().lower())).scalar()


def makes(pi: Engine) -> list[dict]:
    with pi.connect() as conn:
        rows = conn.execute(
            select(pi_make_table.c.name, func.min(_YEAR), func.max(_YEAR))
            .join(pi_car_table, pi_car_table.c.make_id == pi_make_table.c.id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .group_by(pi_make_table.c.name).order_by(pi_make_table.c.name)
        ).all()
    return [{"name": n, "yearMin": a, "yearMax": b} for n, a, b in rows]


def models(pi: Engine, make: str) -> list[dict]:
    """Models of a make with the catalogue years each exists in."""
    with pi.connect() as conn:
        rows = conn.execute(
            select(pi_model_table.c.name, _YEAR).distinct()
            .join(pi_make_table, pi_make_table.c.id == pi_model_table.c.make_id)
            .join(pi_car_table, pi_car_table.c.model_id == pi_model_table.c.id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .where(func.lower(pi_make_table.c.name) == make.strip().lower())
        ).all()
    years: dict[str, set[int]] = {}
    for name, year in rows:
        years.setdefault(name, set()).add(year)
    return [{"name": n, "years": sorted(years[n])} for n in sorted(years)]


def model_exists(pi: Engine, make: str, model: str) -> bool:
    with pi.connect() as conn:
        return conn.execute(
            select(pi_model_table.c.id)
            .join(pi_make_table, pi_make_table.c.id == pi_model_table.c.make_id)
            .where(func.lower(pi_make_table.c.name) == make.strip().lower(), pi_model_table.c.name == model)
            .limit(1)
        ).first() is not None


def trim_exists(pi: Engine, name: str) -> bool:
    with pi.connect() as conn:
        return conn.execute(select(pi_trim_table.c.id).where(pi_trim_table.c.name == name).limit(1)).first() is not None


def _in_range(years: list[int], lo: int | None, hi: int | None) -> int:
    return sum(1 for y in years if (lo is None or y >= lo) and (hi is None or y <= hi))


_CLASS = re.compile(r"^(.*?)-?\s*class$", re.IGNORECASE)


def similarity(decode_name: str, catalogue_name: str) -> float:
    """How alike a decode's model (+ series) and a catalogue model name are, 0..1.

    Plain string similarity, plus a prefix rule for "C-Class"-style decodes, which the catalogue lists
    by variant (C 230, C 300): a catalogue name that starts with the class letters scores high."""
    a, b = name_key(decode_name), name_key(catalogue_name)
    if not a or not b:
        return 0.0
    score = SequenceMatcher(None, a, b).ratio()
    if b.startswith(a) or a.startswith(b):
        score = max(score, 0.8)
    m = _CLASS.match(decode_name.strip())
    if m:
        letters = name_key(m.group(1))
        if letters and b.startswith(letters) and b[len(letters):len(letters) + 1].isdigit():
            score = max(score, 0.85)
    return round(score, 3)


def suggest(pi: Engine, make: str, decode_names: list[str], lo: int | None, hi: int | None,
            limit: int = 12) -> list[dict]:
    """Catalogue models of `make` ranked for a decode: ones that exist in the group's years first, then by
    name similarity. Each carries its years so the admin sees coverage at a glance."""
    out = []
    for m in models(pi, make):
        score = max((similarity(n, m["name"]) for n in decode_names if n), default=0.0)
        out.append({**m, "score": score, "yearsInRange": _in_range(m["years"], lo, hi)})
    out.sort(key=lambda m: (m["yearsInRange"] > 0, m["score"]), reverse=True)
    return [m for m in out if m["score"] >= 0.35][:limit]


@router.get("/makes")
def get_makes(eng=Depends(engines)):
    return makes(eng[1])


@router.get("/models")
def get_models(make: str = Query(..., min_length=1), year_from: int | None = None, year_to: int | None = None,
               eng=Depends(engines)):
    rows = models(eng[1], make)
    for r in rows:
        r["yearsInRange"] = _in_range(r["years"], year_from, year_to)
    return rows


@router.get("/suggest")
def get_suggest(make: str = Query(..., min_length=1), name: list[str] = Query(default=[]),
                year_from: int | None = None, year_to: int | None = None, eng=Depends(engines)):
    """Ranked models of any make for the given decode names (the "different make" case)."""
    cat = catalogue_make(eng[1], make)
    return suggest(eng[1], cat, name, year_from, year_to) if cat else []
