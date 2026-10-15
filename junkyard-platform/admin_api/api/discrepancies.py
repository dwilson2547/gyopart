"""Discrepancy groups (design §2.3). Vehicles with a usable decode group by what NHTSA said (make, model,
series); vehicles without one (no_vin, decode_failed) group by yard + the yard's own make/model strings,
since those are fixed with yard rules."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select, update
from sqlalchemy.orm import Session

from junkyard_common.models import DecodeMapping, Location, MappingDiscrepancy, Vehicle
from pipeline.car_matcher import name_key

from . import catalogue
from .common import BUCKETS, IGNORED, YARD_REASONS, engines, open_discrepancies, sql_year

router = APIRouter(prefix="/api", tags=["discrepancies"])

PAGE = 50
D, V = MappingDiscrepancy, Vehicle


class GroupKey(BaseModel):
    kind: Literal["decode", "yard"]
    make: str | None = None    # NHTSA make (decode) or the yard's raw make (yard)
    model: str | None = None
    series: str | None = None  # decode groups only
    source: str | None = None  # yard groups only


def key_filter(key: GroupKey):
    """WHERE clause selecting a group's discrepancies (joined to Vehicle)."""
    if key.kind == "decode":
        return and_(D.reason.notin_(YARD_REASONS),
                    func.coalesce(D.nhtsa_make, "") == (key.make or ""),
                    func.coalesce(D.nhtsa_model, "") == (key.model or ""),
                    func.coalesce(D.nhtsa_series, "") == (key.series or ""))
    return and_(D.reason.in_(YARD_REASONS), V.source == (key.source or ""),
                func.coalesce(D.raw_make, "") == (key.make or ""),
                func.coalesce(D.raw_model, "") == (key.model or ""))


def _filters(q, kind: str, yard: str | None, make: str | None, search: str | None):
    if yard:
        q = q.where(V.source == yard)
    make_col, model_col = (D.nhtsa_make, D.nhtsa_model) if kind == "decode" else (D.raw_make, D.raw_model)
    if make:
        q = q.where(func.lower(make_col) == make.lower())
    if search:
        like = f"%{search.strip()}%"
        q = q.where(model_col.ilike(like) | make_col.ilike(like) | D.nhtsa_series.ilike(like))
    return q


def _group_rows(session: Session, kind: str, reasons, status: str, yard, make, search) -> list[dict]:
    # One row per decode (or yard + strings), even when its years fall under different reasons.
    if kind == "decode":
        cols = (D.nhtsa_make, D.nhtsa_model, D.nhtsa_series)
        year = sql_year(D.nhtsa_year)
    else:
        cols = (V.source, D.raw_make, D.raw_model)
        year = V.year
    q = (select(*cols, func.count().label("n"), func.min(year), func.max(year),
                func.array_agg(distinct(V.source)), func.array_agg(distinct(D.reason)))
         .select_from(D).join(V, V.id == D.vehicle_id).where(D.reason.in_(reasons)).group_by(*cols))
    q = _filters(open_discrepancies(q, status), kind, yard, make, search)
    out = []
    for a, b, c, n, y0, y1, yards, why in session.execute(q):
        key = (GroupKey(kind="decode", make=a, model=b, series=c) if kind == "decode"
               else GroupKey(kind="yard", source=a, make=b, model=c))
        out.append({"key": key.model_dump(), "reasons": sorted(why), "vehicles": n, "yearMin": y0,
                    "yearMax": y1, "yards": sorted(y for y in yards if y)})
    return out


def groups(session: Session, tab: str, yard=None, make=None, search=None, page: int = 1) -> dict:
    if tab == IGNORED:
        rows = (_group_rows(session, "decode", [r for b in ("fixable", "gaps") for r in BUCKETS[b]], IGNORED,
                            yard, make, search)
                + _group_rows(session, "yard", YARD_REASONS, IGNORED, yard, make, search))
    elif tab in BUCKETS:
        kind = "yard" if tab == "nodecode" else "decode"
        rows = _group_rows(session, kind, BUCKETS[tab], "open", yard, make, search)
    else:
        raise HTTPException(422, f"tab must be one of {sorted([*BUCKETS, IGNORED])}")
    rows.sort(key=lambda g: (-g["vehicles"], str(g["key"])))
    pages = max(1, -(-len(rows) // PAGE))
    page = min(max(page, 1), pages)
    return {"groups": rows[(page - 1) * PAGE: page * PAGE], "total": len(rows), "page": page, "pages": pages}


def summary(session: Session, yard=None, search=None) -> dict:
    """Vehicles and groups per tab."""
    out = {}
    for tab in [*BUCKETS, IGNORED]:
        g = groups(session, tab, yard=yard, search=search)
        out[tab] = {"groups": g["total"], "vehicles": None}
    q = (select(D.reason, D.status == IGNORED, func.count()).join(V, V.id == D.vehicle_id)
         .where(V.is_active.is_(True), V.car_id_resolved.is_(False)).group_by(D.reason, D.status == IGNORED))
    if yard:
        q = q.where(V.source == yard)
    counts = {tab: 0 for tab in out}
    for reason, ignored, n in session.execute(q):
        if ignored:
            counts[IGNORED] += n
        else:
            for tab, reasons in BUCKETS.items():
                if reason in reasons:
                    counts[tab] += n
    for tab in out:
        out[tab]["vehicles"] = counts[tab]
    return out


def detail(session: Session, pi, key: GroupKey, status: str = "open") -> dict:
    year = sql_year(D.nhtsa_year) if key.kind == "decode" else V.year

    def counts(col):
        q = open_discrepancies(select(col, func.count()).select_from(D).join(V, V.id == D.vehicle_id)
                               .where(key_filter(key)),
                               status).group_by(col).order_by(func.count().desc())
        return [{"value": v, "vehicles": n} for v, n in session.execute(q)]

    by_year = sorted(counts(year), key=lambda r: (r["value"] is None, r["value"]))
    samples = session.execute(
        open_discrepancies(
            select(V.id, V.vin, V.source, V.source_key, V.year, V.make, V.model, V.trim, V.row, V.arrival_date,
                   Location.name, D.reason)
            .join(D, D.vehicle_id == V.id).join(Location, Location.id == V.location_id)
            .where(key_filter(key)), status)
        .order_by(V.arrival_date.desc().nullslast(), V.id.desc()).limit(30)
    ).all()
    by_reason = counts(D.reason)
    total = sum(r["vehicles"] for r in by_reason)
    if total == 0:
        raise HTTPException(404, "no open vehicles in this group (it may have just been fixed)")
    years = [r["value"] for r in by_year if r["value"] is not None]
    lo, hi = (min(years), max(years)) if years else (None, None)
    out = {
        "key": key.model_dump(), "status": status, "vehicles": total, "yearMin": lo, "yearMax": hi,
        "byReason": by_reason, "byYard": counts(V.source), "byYear": by_year,
        "samples": [{"id": r[0], "vin": r[1], "source": r[2], "stock": r[3], "year": r[4], "make": r[5],
                     "model": r[6], "trim": r[7], "row": r[8],
                     "arrived": r[9].isoformat() if r[9] else None, "location": r[10], "reason": r[11]}
                    for r in samples],
    }
    if key.kind == "decode":
        cat_make = catalogue.catalogue_make(pi, key.make)
        names = [f"{key.model} {key.series}" if key.series else None, key.model]
        out["catalogueMake"] = cat_make
        out["makeYears"] = next((m for m in catalogue.makes(pi) if m["name"] == cat_make), None)
        out["suggestions"] = catalogue.suggest(pi, cat_make, names, lo, hi) if cat_make else []
        out["mappings"] = [
            {"id": m.id, "series": m.nhtsa_series, "yearFrom": m.year_from, "yearTo": m.year_to,
             "make": m.catalogue_make, "model": m.catalogue_model}
            for m in session.execute(select(DecodeMapping).where(
                DecodeMapping.make_key == name_key(key.make), DecodeMapping.model_key == name_key(key.model)
            ).order_by(DecodeMapping.id)).scalars()]
    else:
        all_makes = catalogue.makes(pi)
        make_sugg = sorted(({"name": m["name"], "score": catalogue.similarity(key.make or "", m["name"])}
                            for m in all_makes), key=lambda m: -m["score"])[:8]
        best = catalogue.catalogue_make(pi, key.make) or (make_sugg[0]["name"] if make_sugg else None)
        out["catalogueMake"] = catalogue.catalogue_make(pi, key.make)
        out["makeSuggestions"] = [m for m in make_sugg if m["score"] >= 0.35]
        out["modelSuggestions"] = (catalogue.suggest(pi, best, [key.model or ""], lo, hi) if best else [])
        out["modelSuggestionsMake"] = best
    return out


def set_status(session: Session, key: GroupKey, ignore: bool) -> int:
    ids = select(D.id).join(V, V.id == D.vehicle_id).where(key_filter(key))
    ids = open_discrepancies(ids, "open" if ignore else IGNORED)
    return session.execute(update(D).where(D.id.in_(ids)).values(status=IGNORED if ignore else "unresolved")
                           .execution_options(synchronize_session=False)).rowcount or 0


# ── routes ─────────────────────────────────────────────────────────────────────────────────────────

@router.get("/discrepancies/summary")
def get_summary(yard: str | None = None, q: str | None = None, eng=Depends(engines)):
    with Session(eng[0]) as s:
        return summary(s, yard=yard, search=q)


@router.get("/discrepancies/groups")
def get_groups(tab: str = "fixable", yard: str | None = None, make: str | None = None, q: str | None = None,
               page: int = Query(1, ge=1), eng=Depends(engines)):
    with Session(eng[0]) as s:
        return groups(s, tab, yard=yard, make=make, search=q, page=page)


class DetailRequest(BaseModel):
    key: GroupKey
    status: Literal["open", "ignored"] = "open"


@router.post("/discrepancies/group")
def post_detail(body: DetailRequest, eng=Depends(engines)):
    with Session(eng[0]) as s:
        return detail(s, eng[1], body.key, body.status)


class StatusRequest(BaseModel):
    key: GroupKey
    ignore: bool


@router.post("/discrepancies/status")
def post_status(body: StatusRequest, eng=Depends(engines)):
    with Session(eng[0]) as s:
        n = set_status(s, body.key, body.ignore)
        s.commit()
    return {"updated": n}


@router.get("/yards")
def get_yards(eng=Depends(engines)):
    with Session(eng[0]) as s:
        rows = s.execute(
            select(V.source, func.count(), func.count().filter(V.car_id_resolved.is_(False)))
            .where(V.is_active.is_(True)).group_by(V.source).order_by(V.source)).all()
    return [{"source": a, "vehicles": n, "unmatched": u} for a, n, u in rows]
