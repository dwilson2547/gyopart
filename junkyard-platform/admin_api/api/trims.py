"""Trim groups and trim mappings (matching-v2-design §2.2-2.3).

A trim group is the matched-but-ambiguous vehicles whose candidates differ by trim and whose trim text the matcher
couldn't read (vehicles.car_id_trim_unread), by decode make, model and that text. A trim mapping settles the text:
`map` to one or more catalogue trims, or `noise` (it carries no trim). Like decode mappings: preview first (the
real matcher over cached decodes), create requeues the affected vehicles, targets must exist in the catalogue.
"""
from __future__ import annotations

import datetime
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from junkyard_common.models import Location, TrimMapping as TrimMappingRow, Vehicle, VinCache
from pipeline.car_matcher import TrimMapping, match_decoded, name_key
from pipeline.pi_schema import pi_car_table, pi_model_table, pi_trim_table, pi_year_table
from pipeline.resolution_pipeline import load_mappings, load_trim_mappings

from . import catalogue
from ..auth.web import who
from .common import engines, requeue, sql_key, sql_year

router = APIRouter(prefix="/api", tags=["trims"])

V = Vehicle
UNREAD = "trim_unread"   # the group "reason" shown in lists
_MATCH_FIELDS = ("ModelYear", "Make", "Model", "Series", "Trim", "DisplacementL", "EngineCylinders",
                 "FuelTypePrimary", "FuelTypeSecondary", "ElectrificationLevel")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _invalid(field: str, message: str):
    raise HTTPException(422, {"field": field, "message": message})


# ── groups ─────────────────────────────────────────────────────────────────────────────────────────

def _unread():
    """Active, ambiguous vehicles with trim text nobody could read, joined to their decode."""
    return (select().select_from(V).join(VinCache, VinCache.vin == V.vin)
            .where(V.is_active.is_(True), V.car_id_method == "vin_candidates", V.car_id_trim_unread.isnot(None)))


def _group_where(make: str | None, model: str | None, trim: str | None):
    return [func.coalesce(VinCache.make, "") == (make or ""), func.coalesce(VinCache.model, "") == (model or ""),
            V.car_id_trim_unread == (trim or "")]


def groups(session: Session, yard=None, make=None, search=None) -> list[dict]:
    year = sql_year(VinCache.model_year)
    q = (_unread().add_columns(VinCache.make, VinCache.model, V.car_id_trim_unread, func.count(), func.min(year),
                               func.max(year), func.array_agg(distinct(V.source)))
         .group_by(VinCache.make, VinCache.model, V.car_id_trim_unread))
    if yard:
        q = q.where(V.source == yard)
    if make:
        q = q.where(func.lower(VinCache.make) == make.lower())
    if search:
        like = f"%{search.strip()}%"
        q = q.where(VinCache.make.ilike(like) | VinCache.model.ilike(like) | V.car_id_trim_unread.ilike(like))
    return [{"key": {"kind": "trim", "make": mk, "model": md, "series": None, "source": None, "trim": tr},
             "reasons": [UNREAD], "vehicles": n, "yearMin": y0, "yearMax": y1, "yards": sorted(y for y in yards if y)}
            for mk, md, tr, n, y0, y1, yards in session.execute(q)]


def _candidate_trims(pi, candidate_lists: list[list[int]]) -> list[dict]:
    """The catalogue trims among the group's candidates: how many vehicles could be each, models and years."""
    ids = {i for c in candidate_lists for i in c}
    if not ids:
        return []
    with pi.connect() as conn:
        rows = conn.execute(
            select(pi_car_table.c.id, pi_trim_table.c.name, pi_model_table.c.name, pi_year_table.c.name)
            .join(pi_model_table, pi_model_table.c.id == pi_car_table.c.model_id)
            .join(pi_year_table, pi_year_table.c.id == pi_car_table.c.year_id)
            .outerjoin(pi_trim_table, pi_trim_table.c.id == pi_car_table.c.trim_id)
            .where(pi_car_table.c.id.in_(ids))).all()
    car = {r[0]: r for r in rows}
    vehicles: Counter = Counter()
    models: dict[str, set] = {}
    years: dict[str, set] = {}
    for c in candidate_lists:
        names = {car[i][1] for i in c if i in car and car[i][1]}
        vehicles.update(names)
        for i in c:
            if i in car and car[i][1]:
                models.setdefault(car[i][1], set()).add(car[i][2])
                years.setdefault(car[i][1], set()).add(int(car[i][3]))
    return [{"name": n, "vehicles": vehicles[n], "models": sorted(models[n]), "years": sorted(years[n])}
            for n in sorted(vehicles, key=lambda n: (-vehicles[n], n))]


def detail(session: Session, pi, make: str | None, model: str | None, trim: str | None) -> dict:
    where = _group_where(make, model, trim)
    year = sql_year(VinCache.model_year)

    def counts(col):
        q = _unread().add_columns(col, func.count()).where(*where).group_by(col).order_by(func.count().desc())
        return [{"value": v, "vehicles": n} for v, n in session.execute(q)]

    by_year = sorted(counts(year), key=lambda r: (r["value"] is None, r["value"]))
    total = sum(r["vehicles"] for r in by_year)
    if total == 0:
        raise HTTPException(404, "no ambiguous vehicles with this trim text (it may have just been settled)")
    cands = [list(c or []) for c in session.execute(_unread().add_columns(V.car_id_candidates).where(*where)).scalars()]
    samples = session.execute(
        _unread().add_columns(V.id, V.vin, V.source, V.source_key, V.year, V.make, V.model, V.trim, V.row,
                              V.arrival_date, Location.name, VinCache.raw["Series"].astext)
        .join(Location, Location.id == V.location_id).where(*where)
        .order_by(V.arrival_date.desc().nullslast(), V.id.desc()).limit(30)).all()
    yrs = [r["value"] for r in by_year if r["value"] is not None]
    mappings = session.execute(select(TrimMappingRow).where(
        TrimMappingRow.make_key == name_key(make), TrimMappingRow.trim_key == name_key(trim))
        .order_by(TrimMappingRow.id)).scalars().all()
    return {
        "key": {"kind": "trim", "make": make, "model": model, "series": None, "source": None, "trim": trim},
        "status": "open", "vehicles": total, "yearMin": min(yrs) if yrs else None, "yearMax": max(yrs) if yrs else None,
        "byReason": [{"value": UNREAD, "vehicles": total}], "byYard": counts(V.source), "byYear": by_year,
        "samples": [{"id": r[0], "vin": r[1], "source": r[2], "stock": r[3], "year": r[4], "make": r[5],
                     "model": r[6], "trim": r[7], "row": r[8], "arrived": r[9].isoformat() if r[9] else None,
                     "location": r[10], "reason": UNREAD, "series": r[11]} for r in samples],
        "catalogueMake": catalogue.catalogue_make(pi, make),
        "candidateTrims": _candidate_trims(pi, cands),
        "trimMappings": [_mapping_out(m) for m in mappings],
    }


# ── trim mappings ──────────────────────────────────────────────────────────────────────────────────

class TrimMappingRequest(BaseModel):
    make: str = Field(min_length=1)          # the decode's make and model, from the group
    model: str | None = None                 # None = every model of the make
    trim: str = Field(min_length=1)          # the trim text, from the group
    year_from: int | None = None
    year_to: int | None = None
    action: Literal["map", "noise"] = "map"
    trims: list[str] = Field(default_factory=list)   # catalogue trims, for map

    @model_validator(mode="after")
    def _check(self):
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from is after year_to")
        if self.action == "map" and not self.trims:
            raise ValueError("pick at least one catalogue trim")
        if self.action == "noise":
            self.trims = []
        return self

    def mapping(self) -> TrimMapping:
        return TrimMapping(name_key(self.make), name_key(self.model) if self.model else None, name_key(self.trim),
                           self.year_from, self.year_to, self.action, tuple(self.trims))


def _check_trims(pi, req: TrimMappingRequest) -> None:
    for i, t in enumerate(req.trims):
        if not catalogue.trim_exists(pi, t):
            _invalid(f"trims.{i}", f"{t} is not a catalogue trim")


def _covered(make: str, model: str | None, trim: str, year_from, year_to):
    """Active VIN-matched vehicles whose decode (or yard) trim text is this one, for this make/model and years:
    everything a trim mapping for it can change."""
    key = name_key(trim)
    conds = [V.is_active.is_(True), V.car_id_method.in_(("vin_candidates", "vin_exact")),
             sql_key(VinCache.make) == name_key(make),
             or_(sql_key(VinCache.raw["Trim"].astext) == key, sql_key(VinCache.raw["Series"].astext) == key,
                 sql_key(V.trim) == key)]
    if model:
        conds.append(sql_key(VinCache.model) == name_key(model))
    year = sql_year(VinCache.model_year)
    if year_from:
        conds.append(year >= year_from)
    if year_to:
        conds.append(year <= year_to)
    return conds


def covered_vehicles(session: Session, req: TrimMappingRequest) -> list[tuple]:
    q = (select(V.id, VinCache.raw, V.trim, V.car_id_candidates).join(VinCache, VinCache.vin == V.vin)
         .where(*_covered(req.make, req.model, req.trim, req.year_from, req.year_to)))
    return list(session.execute(q))


def simulate(pi, rows: list[tuple], mappings, trim_mappings) -> dict:
    """Re-run the matcher over the covered vehicles: how many end exact, narrower, unchanged, wider."""
    memo: dict[tuple, object] = {}
    tally: Counter = Counter()
    for _, raw, yard_trim, cands in rows:
        raw = raw or {}
        k = (*(raw.get(f) for f in _MATCH_FIELDS), yard_trim)
        if k not in memo:
            memo[k] = match_decoded(raw, pi, mappings, yard_trim, trim_mappings)
        before, after = len(cands or []), len(memo[k].candidates)
        tally["exactBefore"] += before == 1
        tally["exact"] += after == 1
        tally["narrower" if after < before else "wider" if after > before else "unchanged"] += 1
    return {"vehicles": len(rows), "exact": tally["exact"], "exactBefore": tally["exactBefore"],
            "narrower": tally["narrower"], "unchanged": tally["unchanged"], "wider": tally["wider"]}


def _existing(session: Session, req: TrimMappingRequest) -> TrimMappingRow | None:
    m = req.mapping()
    return session.execute(select(TrimMappingRow).where(
        TrimMappingRow.make_key == m.make_key, TrimMappingRow.trim_key == m.trim_key,
        (TrimMappingRow.model_key == m.model_key) if m.model_key else TrimMappingRow.model_key.is_(None),
        func.coalesce(TrimMappingRow.year_from, 0) == (m.year_from or 0),
        func.coalesce(TrimMappingRow.year_to, 0) == (m.year_to or 0))).scalars().first()


def preview_trim_mapping_for(eng, req: TrimMappingRequest) -> dict:
    ji, pi = eng
    _check_trims(pi, req)
    with Session(ji) as s:
        rows = covered_vehicles(s, req)
        mappings, trim_mappings = load_mappings(s), load_trim_mappings(s)
    # The new mapping first, so it wins over an existing one for the same text (create refuses exact duplicates).
    return simulate(pi, rows, mappings, [req.mapping(), *trim_mappings])


def save_trim_mapping(eng, req: TrimMappingRequest, by: str) -> dict:
    ji, pi = eng
    _check_trims(pi, req)
    with Session(ji) as s:
        if (dup := _existing(s, req)) is not None:
            _invalid("trim", f"trim mapping {dup.id} already covers this text for these years; delete it first")
        m = req.mapping()
        row = TrimMappingRow(nhtsa_make=req.make, nhtsa_model=req.model, trim_text=req.trim[:200],
                             make_key=m.make_key, model_key=m.model_key, trim_key=m.trim_key,
                             year_from=req.year_from, year_to=req.year_to, action=req.action,
                             catalogue_trims=list(req.trims) or None, created_by=by[:100], created_at=_now())
        s.add(row)
        s.flush()
        requeued = requeue(s, [r[0] for r in covered_vehicles(s, req)], include_matched=True)
        s.commit()
        return {"created": row.id, "requeued": requeued}


def _mapping_out(m: TrimMappingRow) -> dict:
    return {"id": m.id, "nhtsaMake": m.nhtsa_make, "nhtsaModel": m.nhtsa_model, "trim": m.trim_text,
            "yearFrom": m.year_from, "yearTo": m.year_to, "action": m.action, "trims": list(m.catalogue_trims or []),
            "createdBy": m.created_by, "createdAt": m.created_at.isoformat()}


def list_trim_mappings(eng) -> list[dict]:
    with Session(eng[0]) as s:
        rows = s.execute(select(TrimMappingRow).order_by(TrimMappingRow.nhtsa_make, TrimMappingRow.trim_text,
                                                          TrimMappingRow.id)).scalars().all()
        out = []
        for m in rows:
            n = s.execute(select(func.count()).select_from(V).join(VinCache, VinCache.vin == V.vin).where(
                *_covered(m.nhtsa_make, m.nhtsa_model, m.trim_text, m.year_from, m.year_to))).scalar()
            out.append({**_mapping_out(m), "vehicles": n})
    return out


def remove_trim_mapping(eng, mapping_id: int, created_by_prefix: str | None = None) -> dict:
    """Delete a trim mapping and requeue every vehicle it covered. With created_by_prefix, only one whose creator
    starts with it (the MCP may delete only what agents made)."""
    with Session(eng[0]) as s:
        m = s.get(TrimMappingRow, mapping_id)
        if m is None:
            raise HTTPException(404, "trim mapping not found")
        if created_by_prefix and not (m.created_by or "").startswith(created_by_prefix):
            raise HTTPException(403, f"trim mapping {mapping_id} was made by {m.created_by}, not by an agent; "
                                     "only the user can delete it, in the admin UI")
        ids = list(s.execute(select(V.id).join(VinCache, VinCache.vin == V.vin).where(
            *_covered(m.nhtsa_make, m.nhtsa_model, m.trim_text, m.year_from, m.year_to))).scalars())
        s.delete(m)
        requeued = requeue(s, ids, include_matched=True)
        s.commit()
    return {"deleted": mapping_id, "requeued": requeued}


# ── routes ─────────────────────────────────────────────────────────────────────────────────────────

@router.post("/trim-mappings/preview")
def preview_trim_mapping(req: TrimMappingRequest, eng=Depends(engines)):
    return preview_trim_mapping_for(eng, req)


@router.post("/trim-mappings")
def create_trim_mapping(req: TrimMappingRequest, request: Request, eng=Depends(engines)):
    return save_trim_mapping(eng, req, who(request))


@router.get("/trim-mappings")
def get_trim_mappings(eng=Depends(engines)):
    return list_trim_mappings(eng)


@router.delete("/trim-mappings/{mapping_id}")
def delete_trim_mapping(mapping_id: int, eng=Depends(engines)):
    return remove_trim_mapping(eng, mapping_id)
