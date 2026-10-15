"""Shared pieces of the JSON API behind the admin SPA (docs/admin-rewrite-design.md §2.3-2.5).

The API never does bulk work in the web process: fixes write rows (mappings, rules, ignores) and
requeue the affected vehicles; the vin-resolver worker re-matches them within seconds.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import case, func, literal, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import MappingDiscrepancy, Vehicle

# Tabs on the discrepancies page: which reasons each one shows.
BUCKETS: dict[str, tuple[str, ...]] = {
    "fixable": ("model_not_in_catalogue", "make_not_in_catalogue"),
    "gaps": ("year_not_in_catalogue", "model_year_gap"),
    "nodecode": ("no_vin", "decode_failed"),
}
YARD_REASONS = BUCKETS["nodecode"]  # grouped by the yard's own strings, fixed with yard rules
IGNORED = "ignored"


def engines() -> tuple[Engine, Engine]:
    from admin_api.main import _engine, _pi_engine
    if _engine is None or _pi_engine is None:
        raise HTTPException(503, "service not ready (needs JUNKYARD_DATABASE_URL and PARTS_DATABASE_URL)")
    return _engine, _pi_engine


def sql_key(col):
    """SQL twin of pipeline.car_matcher.name_key: lower, & -> and, drop everything but [a-z0-9]."""
    return func.regexp_replace(func.lower(func.replace(func.coalesce(col, literal("")), "&", "and")),
                               "[^a-z0-9]+", "", "g")


def sql_year(col):
    """A 4-digit year string as an int, else NULL."""
    return case((col.op("~")(r"^\d{4}$"), func.cast(col, Vehicle.year.type)), else_=None)


def open_discrepancies(q, status: str = "open"):
    """Limit a query joined to Vehicle + MappingDiscrepancy to active, unmatched vehicles in this status."""
    q = q.where(Vehicle.is_active.is_(True), Vehicle.car_id_resolved.is_(False))
    if status == IGNORED:
        return q.where(MappingDiscrepancy.status == IGNORED)
    return q.where(MappingDiscrepancy.status != IGNORED)


def requeue(session: Session, vehicle_ids: list[int], include_matched: bool = False) -> int:
    """Hand vehicles back to the worker. Unmatched ones only need the queue marker cleared; matched ones
    (a deleted mapping may have been why they matched) are reset too."""
    if not vehicle_ids:
        return 0
    stmt = update(Vehicle).where(Vehicle.id.in_(vehicle_ids))
    if include_matched:
        stmt = stmt.values(car_id_resolved=False, car_id=None, car_id_method=None, car_id_confidence=None,
                           car_id_candidates=None, resolve_attempted_at=None)
    else:
        stmt = stmt.where(Vehicle.car_id_resolved.is_(False)).values(resolve_attempted_at=None)
    return session.execute(stmt).rowcount or 0
