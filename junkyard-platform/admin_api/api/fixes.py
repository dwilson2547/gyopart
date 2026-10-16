"""Fixes (design §2.2-2.5): decode mappings for vehicles with a usable decode, yard rules for the rest.

Every fix has a preview that runs the real matcher over the affected vehicles (cached decodes, so no NHTSA
calls) and a create that writes the rows and requeues exactly those vehicles. Targets must exist in the
catalogue; the API refuses anything else, so a typo can't get in.
"""
from __future__ import annotations

import datetime
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from junkyard_common.models import DecodeMapping, MappingDiscrepancy, MappingRule, Vehicle, VinCache
from pipeline.car_matcher import Mapping, match_decoded, name_key
from pipeline.resolution_pipeline import load_mappings
from pipeline.ymmt_matcher import match_car

from . import catalogue
from ..auth.web import who
from .common import IGNORED, YARD_REASONS, engines, requeue, sql_key, sql_year

router = APIRouter(prefix="/api", tags=["fixes"])
D, V = MappingDiscrepancy, Vehicle

# The decode fields match_decoded reads; vehicles whose decodes agree on these match identically.
_MATCH_FIELDS = ("ModelYear", "Make", "Model", "Series", "Trim", "DisplacementL", "EngineCylinders",
                 "FuelTypePrimary", "FuelTypeSecondary", "ElectrificationLevel")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _invalid(field: str, message: str):
    raise HTTPException(422, {"field": field, "message": message})


# ── decode mappings ────────────────────────────────────────────────────────────────────────────────

class Target(BaseModel):
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)


class MappingRequest(BaseModel):
    make: str = Field(min_length=1)          # the decode's make/model, from the group
    model: str = Field(min_length=1)
    series: str | None = None                # None = any series
    year_from: int | None = None
    year_to: int | None = None
    targets: list[Target] = Field(min_length=1)

    @model_validator(mode="after")
    def _years(self):
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from is after year_to")
        return self

    def mappings(self) -> list[Mapping]:
        return [Mapping(name_key(self.make), name_key(self.model), name_key(self.series) if self.series else None,
                        self.year_from, self.year_to, t.make, t.model) for t in self.targets]


def _check_targets(pi, targets: list[Target]) -> None:
    for i, t in enumerate(targets):
        if not catalogue.model_exists(pi, t.make, t.model):
            _invalid(f"targets.{i}", f"{t.make} {t.model} is not in the catalogue")


def _decode_where(make: str, model: str, series: str | None, year_from, year_to,
                  make_col, model_col, series_col, year_col):
    conds = [make_col == name_key(make), model_col == name_key(model)]
    if series:
        conds.append(series_col == name_key(series))
    if year_from:
        conds.append(year_col >= year_from)
    if year_to:
        conds.append(year_col <= year_to)
    return conds


def mapping_vehicles(session: Session, req: MappingRequest) -> list[tuple[int, dict]]:
    """Open, unmatched vehicles this mapping covers, with their cached decodes."""
    q = (select(V.id, VinCache.raw).join(D, D.vehicle_id == V.id).join(VinCache, VinCache.vin == V.vin)
         .where(V.is_active.is_(True), V.car_id_resolved.is_(False), D.status != IGNORED,
                D.reason.notin_(YARD_REASONS),
                *_decode_where(req.make, req.model, req.series, req.year_from, req.year_to,
                               sql_key(D.nhtsa_make), sql_key(D.nhtsa_model), sql_key(D.nhtsa_series),
                               sql_year(D.nhtsa_year))))
    return [(vid, raw or {}) for vid, raw in session.execute(q)]


def simulate_mapping(pi, raws: list[dict], mappings: list[Mapping]) -> dict:
    memo: dict[tuple, object] = {}
    tally: Counter = Counter()
    for raw in raws:
        k = tuple(raw.get(f) for f in _MATCH_FIELDS)
        if k not in memo:
            memo[k] = match_decoded(raw, pi, mappings)
        m = memo[k]
        if m.candidates:
            tally["match"] += 1
            tally["exact"] += m.exact
        else:
            tally[m.reason] += 1
    return {"vehicles": len(raws), "wouldMatch": tally.pop("match", 0), "exact": tally.pop("exact", 0),
            "unmatched": dict(tally.most_common())}


@router.post("/mappings/preview")
def preview_mapping(req: MappingRequest, eng=Depends(engines)):
    ji, pi = eng
    _check_targets(pi, req.targets)
    with Session(ji) as s:
        rows = mapping_vehicles(s, req)
        existing = load_mappings(s)
    return simulate_mapping(pi, [raw for _, raw in rows], existing + req.mappings())


@router.post("/mappings")
def create_mapping(req: MappingRequest, request: Request, eng=Depends(engines)):
    ji, pi = eng
    _check_targets(pi, req.targets)
    now = _now()
    with Session(ji) as s:
        have = {(m.make_key, m.model_key, m.series_key, m.year_from, m.year_to, m.catalogue_make, m.catalogue_model)
                for m in load_mappings(s)}
        created = 0
        for m in req.mappings():
            if (m.make_key, m.model_key, m.series_key, m.year_from, m.year_to, m.catalogue_make,
                    m.catalogue_model) in have:
                continue
            s.add(DecodeMapping(nhtsa_make=req.make, nhtsa_model=req.model, nhtsa_series=req.series,
                                make_key=m.make_key, model_key=m.model_key, series_key=m.series_key,
                                year_from=req.year_from, year_to=req.year_to, catalogue_make=m.catalogue_make,
                                catalogue_model=m.catalogue_model, created_by=who(request), created_at=now))
            created += 1
        requeued = requeue(s, [vid for vid, _ in mapping_vehicles(s, req)])
        s.commit()
    return {"created": created, "requeued": requeued}


def _mapping_decode_vehicles(session: Session, m: DecodeMapping):
    """Active vehicles whose decode this mapping covers, matched or not."""
    series = func.coalesce(VinCache.raw["Series"].astext, "")
    return (select(V.id, V.car_id_resolved).join(VinCache, VinCache.vin == V.vin)
            .where(V.is_active.is_(True),
                   *_decode_where(m.nhtsa_make, m.nhtsa_model, m.nhtsa_series, m.year_from, m.year_to,
                                  sql_key(VinCache.make), sql_key(VinCache.model), sql_key(series),
                                  sql_year(VinCache.model_year))))


@router.get("/mappings")
def list_mappings(eng=Depends(engines)):
    with Session(eng[0]) as s:
        out = []
        counted: dict[tuple, list] = {}  # one vehicle count per distinct decode, however many targets it has
        for m in s.execute(select(DecodeMapping).order_by(DecodeMapping.nhtsa_make, DecodeMapping.nhtsa_model,
                                                           DecodeMapping.id)).scalars():
            decode = (m.make_key, m.model_key, m.series_key, m.year_from, m.year_to)
            if decode not in counted:
                counted[decode] = s.execute(_mapping_decode_vehicles(s, m)).all()
            rows = counted[decode]
            out.append({"id": m.id, "nhtsaMake": m.nhtsa_make, "nhtsaModel": m.nhtsa_model,
                        "nhtsaSeries": m.nhtsa_series, "yearFrom": m.year_from, "yearTo": m.year_to,
                        "make": m.catalogue_make, "model": m.catalogue_model, "createdBy": m.created_by,
                        "createdAt": m.created_at.isoformat(), "vehicles": len(rows),
                        "matched": sum(1 for _, ok in rows if ok)})
    return out


@router.delete("/mappings/{mapping_id}")
def delete_mapping(mapping_id: int, eng=Depends(engines)):
    with Session(eng[0]) as s:
        m = s.get(DecodeMapping, mapping_id)
        if m is None:
            raise HTTPException(404, "mapping not found")
        ids = [vid for vid, _ in s.execute(_mapping_decode_vehicles(s, m))]
        s.delete(m)
        requeued = requeue(s, ids, include_matched=True)
        s.commit()
    return {"deleted": mapping_id, "requeued": requeued}


# ── yard rules (vehicles without a usable decode) ──────────────────────────────────────────────────

class RuleRequest(BaseModel):
    source: str | None = None                # None = every yard
    raw_make: str | None = None              # the yard's strings, from the group
    raw_model: str | None = None
    make: str = Field(min_length=1)          # catalogue make
    model: str | None = None                 # catalogue model (optional: fix the make only)


def _check_rule(pi, req: RuleRequest) -> str:
    cat_make = catalogue.catalogue_make(pi, req.make)
    if not cat_make:
        _invalid("make", f"{req.make} is not a catalogue make")
    if req.model and not catalogue.model_exists(pi, cat_make, req.model):
        _invalid("model", f"{cat_make} {req.model} is not in the catalogue")
    if req.model and not req.raw_model:
        _invalid("model", "this group has no yard model to map")
    return cat_make


def rule_vehicles(session: Session, req: RuleRequest) -> list[tuple[int, int | None, str | None, str | None]]:
    q = (select(V.id, V.year, V.make, V.model).join(D, D.vehicle_id == V.id)
         .where(V.is_active.is_(True), V.car_id_resolved.is_(False), D.status != IGNORED,
                D.reason.in_(YARD_REASONS),
                func.lower(func.coalesce(D.raw_make, "")) == (req.raw_make or "").lower(),
                func.lower(func.coalesce(D.raw_model, "")) == (req.raw_model or "").lower()))
    if req.source:
        q = q.where(V.source == req.source)
    return list(session.execute(q))


@router.post("/rules/preview")
def preview_rule(req: RuleRequest, eng=Depends(engines)):
    ji, pi = eng
    cat_make = _check_rule(pi, req)
    with Session(ji) as s:
        rows = rule_vehicles(s, req)
    memo: dict[tuple, object] = {}
    matched = 0
    for _, year, make, model in rows:
        k = (year, cat_make, req.model or model or "")
        if k not in memo:
            memo[k] = match_car(year, cat_make, req.model or model or "", pi)
        matched += memo[k] is not None
    return {"vehicles": len(rows), "wouldMatch": matched, "unmatched": {"no_match": len(rows) - matched}}


@router.post("/rules")
def create_rule(req: RuleRequest, request: Request, eng=Depends(engines)):
    ji, pi = eng
    cat_make = _check_rule(pi, req)
    now = _now()
    scope = {"scope": "source" if req.source else "global", "source": req.source}
    with Session(ji) as s:
        created = 0
        if req.raw_make and req.raw_make.strip().lower() != cat_make.lower():
            s.add(MappingRule(**scope, field="make", rule_type="exact", raw_value=req.raw_make,
                              canonical_value=cat_make, priority=100, is_active=True, created_by="manual",
                              created_at=now, applied_count=0, approved_by=who(request), approved_at=now))
            created += 1
        if req.model and req.raw_model and req.raw_model != req.model:
            s.add(MappingRule(**scope, field="model", rule_type="exact", raw_value=req.raw_model,
                              canonical_value=req.model, make_context=cat_make, priority=100, is_active=True,
                              created_by="manual", created_at=now, applied_count=0,
                              approved_by=who(request), approved_at=now))
            created += 1
        if not created:
            _invalid("make", "the yard already says exactly this; nothing to map")
        requeued = requeue(s, [r[0] for r in rule_vehicles(s, req)])
        s.commit()
    return {"created": created, "requeued": requeued}


@router.get("/rules")
def list_rules(eng=Depends(engines)):
    with Session(eng[0]) as s:
        rules = s.execute(select(MappingRule).where(MappingRule.is_active.is_(True))
                          .order_by(MappingRule.field, MappingRule.raw_value)).scalars().all()
        return [{"id": r.id, "scope": r.scope, "source": r.source, "field": r.field, "ruleType": r.rule_type,
                 "raw": r.raw_value, "canonical": r.canonical_value, "makeContext": r.make_context,
                 "appliedCount": r.applied_count, "createdBy": r.approved_by or r.created_by,
                 "createdAt": r.created_at.isoformat()} for r in rules]


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, eng=Depends(engines)):
    """Deactivate a rule and re-match the vehicles it may have matched."""
    with Session(eng[0]) as s:
        r = s.get(MappingRule, rule_id)
        if r is None or not r.is_active:
            raise HTTPException(404, "rule not found")
        r.is_active = False
        q = select(V.id).where(V.is_active.is_(True), V.car_id_method == "rule_applied")
        if r.rule_type == "exact":
            col = V.make if r.field == "make" else V.model if r.field == "model" else V.trim
            q = q.where(func.lower(col) == r.raw_value.lower())
        if r.scope == "source" and r.source:
            q = q.where(V.source == r.source)
        requeued = requeue(s, list(s.execute(q).scalars()), include_matched=True)
        s.commit()
    return {"deleted": rule_id, "requeued": requeued}
