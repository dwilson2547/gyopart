"""
Orchestrates the vehicle-to-car mapping pipeline.

Pipeline steps (in order):
  0. Geocode any Location rows missing lat/lng (using uszipcode)
  1. VIN decode via NHTSA (cached)
  2. Apply MappingRules to transform make/model/trim
  3. Fuzzy YMMT match against parts_interchange (threshold 0.85)
  4. Discrepancy record for failures, with the reason and the NHTSA decode; a later match deletes it

CLI:
  python -m pipeline.resolution_pipeline [--limit N] [--source SOURCE] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from junkyard_common.db import get_engine, get_session
from junkyard_common.models import DecodeMapping, Location, MappingDiscrepancy, MappingRule, Vehicle
from pipeline.rule_engine import apply_rules
from pipeline.car_matcher import DECODE_FAILED, Mapping, decoded_vehicle_fields, match_decoded
from pipeline.vin_decoder import decode_vin, warm_vin_cache_bulk
from pipeline.ymmt_matcher import YmmtMatch, match_car

logger = logging.getLogger(__name__)


def geocode_locations(engine, dry_run: bool = False) -> None:
    from uszipcode import SearchEngine
    sz = SearchEngine()
    with Session(engine) as session:
        locations = session.execute(
            select(Location).where(Location.lat == None, Location.zip_code != None)  # noqa: E711
        ).scalars().all()
        if not locations:
            return
        updated = 0
        for loc in locations:
            result = sz.by_zipcode(loc.zip_code[:5])  # ZIP+4 → ZIP
            if result and result.lat and result.lng:
                loc.lat = result.lat
                loc.lng = result.lng
                updated += 1
            else:
                logger.warning("No geocode result for %s zip=%s", loc.name, loc.zip_code)
        if not dry_run:
            session.commit()
        logger.info("Geocoded %d/%d locations", updated, len(locations))


NO_VIN = "no_vin"


def load_mappings(session: Session) -> list[Mapping]:
    """Every decode mapping, as plain values the matcher can use after the session closes."""
    return [Mapping.of(r) for r in session.execute(select(DecodeMapping)).scalars()]


def _clear_discrepancy(vehicle: Vehicle, session: Session, dry_run: bool) -> None:
    """A vehicle that matches has no discrepancy any more (a manual one included: matched is matched)."""
    if not dry_run:
        session.execute(delete(MappingDiscrepancy).where(MappingDiscrepancy.vehicle_id == vehicle.id))


def _cut(value, n: int) -> str | None:
    value = (value or "").strip()
    return value[:n] or None


def _set_match(vehicle: Vehicle, candidates: list[int], method: str, confidence: float, now: datetime) -> None:
    vehicle.car_id_candidates = candidates
    vehicle.car_id = candidates[0] if len(candidates) == 1 else None
    vehicle.car_id_resolved = True
    vehicle.car_id_method = method
    vehicle.car_id_confidence = confidence
    vehicle.resolve_attempted_at = now


def resolve_vehicle(
    vehicle: Vehicle,
    session: Session,
    pi_engine,
    rules: list[MappingRule],
    dry_run: bool = False,
    decoded: dict | None = None,
    commit: bool = True,
    mappings: list[Mapping] = (),
) -> str:
    """
    Attempt to resolve the catalogue cars a yard vehicle can be. Returns one of:
    "already_resolved" | "vin_exact" | "vin_candidates" | "ymmt_match" | "rule_applied" | "discrepancy"

    `decoded` is the VIN decode when the caller already has it (the worker decodes in batches); otherwise the
    VIN is decoded here, cache-first. `mappings` are the decode mappings (load_mappings).
    """
    if vehicle.car_id_resolved:
        return "already_resolved"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def done(result: str) -> str:
        if commit and not dry_run:
            session.commit()
        return result

    # Step 1: VIN decode, narrowed to trim/engine where the decode allows
    if decoded is None and vehicle.vin:
        decoded = decode_vin(vehicle.vin, session)
    raw = (decoded or {}).get("raw") or {}
    match = None
    if decoded:
        for column, value in decoded_vehicle_fields(raw).items():
            if getattr(vehicle, column) is None:
                setattr(vehicle, column, value)
        match = match_decoded(raw, pi_engine, mappings, vehicle.trim)
        if match.candidates:
            exact = match.exact
            _set_match(vehicle, match.candidates, "vin_exact" if exact else "vin_candidates",
                       1.0 if exact else round(1.0 / len(match.candidates), 4), now)
            _clear_discrepancy(vehicle, session, dry_run)
            return done("vin_exact" if exact else "vin_candidates")

    # Step 2: Apply rules to transform make/model/trim
    transformed, applied_rules = apply_rules(vehicle, rules, session, dry_run=dry_run, commit=commit)

    # Step 3: Fuzzy YMMT match
    ymmt: YmmtMatch | None = match_car(
        vehicle.year, transformed["make"], transformed["model"], pi_engine
    )

    if ymmt is not None:
        method = "rule_applied" if applied_rules else "ymmt_match"
        _set_match(vehicle, ymmt.candidates or [ymmt.car_id], method, ymmt.confidence, now)
        _clear_discrepancy(vehicle, session, dry_run)
        return done(method)

    # Step 4: Discrepancy, with why and what NHTSA said
    vehicle.resolve_attempted_at = now
    if not vehicle.vin:
        reason = NO_VIN
    elif match is None:
        reason = DECODE_FAILED  # VIN present but undecodable (pre-1980, incomplete, malformed)
    else:
        reason = match.reason
    fields = dict(
        raw_year=str(vehicle.year) if vehicle.year else None,
        raw_make=vehicle.make,
        raw_model=vehicle.model,
        raw_trim=vehicle.trim,
        fuzzy_make_match=ymmt.make_match if ymmt else None,
        fuzzy_make_score=ymmt.make_score if ymmt else None,
        fuzzy_model_match=ymmt.model_match if ymmt else None,
        fuzzy_model_score=ymmt.model_score if ymmt else None,
        candidate_car_id=ymmt.car_id if ymmt else None,
        reason=reason,
        nhtsa_year=_cut(raw.get("ModelYear"), 10),
        nhtsa_make=_cut(raw.get("Make"), 100),
        nhtsa_model=_cut(raw.get("Model"), 200),
        nhtsa_series=_cut(raw.get("Series"), 200),
        last_processed_at=now,
    )
    if not dry_run:
        existing = session.execute(
            select(MappingDiscrepancy).where(MappingDiscrepancy.vehicle_id == vehicle.id)
        ).scalar_one_or_none()
        if existing is not None:
            # Refresh what we know; keep the row's status, so an ignored vehicle stays ignored.
            for name, value in fields.items():
                setattr(existing, name, value)
        else:
            session.add(MappingDiscrepancy(vehicle_id=vehicle.id, status="unresolved", created_at=now, **fields))
    return done("discrepancy")


def run_pipeline(
    limit: int | None = None,
    source: str | None = None,
    dry_run: bool = False,
) -> None:
    ji_engine = get_engine()
    pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"])

    geocode_locations(ji_engine, dry_run=dry_run)

    with get_session(ji_engine) as session:
        q = (
            select(Vehicle)
            .where(Vehicle.car_id_resolved == False)  # noqa: E712
            .order_by(Vehicle.id)
        )
        if source:
            q = q.where(Vehicle.source == source)
        if limit:
            q = q.limit(limit)

        vehicles = session.execute(q).scalars().all()
        rules = session.execute(
            select(MappingRule)
            .where(MappingRule.is_active == True)  # noqa: E712
            .order_by(MappingRule.scope, MappingRule.priority)
        ).scalars().all()
        mappings = load_mappings(session)

    all_vins = [v.vin for v in vehicles if v.vin]
    if all_vins:
        warm_vin_cache_bulk(all_vins, ji_engine)

    counts: dict[str, int] = {}
    for vehicle in vehicles:
        with get_session(ji_engine) as session:
            vehicle = session.get(Vehicle, vehicle.id)
            if vehicle is None:
                continue
            result = resolve_vehicle(vehicle, session, pi_engine, rules, dry_run, mappings=mappings)
            counts[result] = counts.get(result, 0) + 1

        processed = sum(counts.values())
        if processed % 100 == 0:
            print(f"Processed {processed}: {counts}")

    print(f"Done. Final counts: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run vehicle-to-car mapping pipeline")
    parser.add_argument("--limit",  type=int,  default=None, help="Max vehicles to process")
    parser.add_argument("--source", type=str,  default=None, help="Filter by source name")
    parser.add_argument("--dry-run", action="store_true",   help="Read-only, no DB writes")
    args = parser.parse_args()
    run_pipeline(limit=args.limit, source=args.source, dry_run=args.dry_run)
