"""
Orchestrates the vehicle-to-car mapping pipeline.

Pipeline steps (in order):
  0. Geocode any Location rows missing lat/lng (using uszipcode)
  1. VIN decode via NHTSA (cached)
  2. Apply MappingRules to transform make/model/trim
  3. Fuzzy YMMT match against parts_interchange (threshold 0.85)
  4. Discrepancy record for failures

CLI:
  python -m pipeline.resolution_pipeline [--limit N] [--source SOURCE] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from junkyard_common.db import get_engine, get_session
from junkyard_common.models import Location, MappingDiscrepancy, MappingRule, Vehicle
from pipeline.rule_engine import apply_rules
from pipeline.car_matcher import decoded_vehicle_fields, match_decoded
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
            result = sz.by_zipcode(loc.zip_code)
            if result and result.lat and result.lng:
                loc.lat = result.lat
                loc.lng = result.lng
                updated += 1
            else:
                logger.warning("No geocode result for %s zip=%s", loc.name, loc.zip_code)
        if not dry_run:
            session.commit()
        logger.info("Geocoded %d/%d locations", updated, len(locations))


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
) -> str:
    """
    Attempt to resolve the catalogue cars a yard vehicle can be. Returns one of:
    "already_resolved" | "vin_exact" | "vin_candidates" | "ymmt_match" | "rule_applied" | "discrepancy"

    `decoded` is the VIN decode when the caller already has it (the worker decodes in batches); otherwise the
    VIN is decoded here, cache-first.
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
    if decoded:
        raw = decoded.get("raw") or {}
        for column, value in decoded_vehicle_fields(raw).items():
            if getattr(vehicle, column) is None:
                setattr(vehicle, column, value)
        match = match_decoded(raw, pi_engine)
        if match.candidates:
            exact = match.exact
            _set_match(vehicle, match.candidates, "vin_exact" if exact else "vin_candidates",
                       1.0 if exact else round(1.0 / len(match.candidates), 4), now)
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
        return done(method)

    # Step 4: Discrepancy
    vehicle.resolve_attempted_at = now
    discrepancy = MappingDiscrepancy(
        vehicle_id=vehicle.id,
        raw_year=str(vehicle.year) if vehicle.year else None,
        raw_make=vehicle.make,
        raw_model=vehicle.model,
        raw_trim=vehicle.trim,
        fuzzy_make_match=ymmt.make_match if ymmt else None,
        fuzzy_make_score=ymmt.make_score if ymmt else None,
        fuzzy_model_match=ymmt.model_match if ymmt else None,
        fuzzy_model_score=ymmt.model_score if ymmt else None,
        candidate_car_id=ymmt.car_id if ymmt else None,
        status="unresolved",
        created_at=now,
        last_processed_at=now,
    )
    if not dry_run:
        existing = session.execute(
            select(MappingDiscrepancy).where(MappingDiscrepancy.vehicle_id == vehicle.id)
        ).scalar_one_or_none()
        if existing is not None:
            discrepancy.id = existing.id
            discrepancy.created_at = existing.created_at
        session.merge(discrepancy)
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

    all_vins = [v.vin for v in vehicles if v.vin]
    if all_vins:
        warm_vin_cache_bulk(all_vins, ji_engine)

    counts: dict[str, int] = {}
    for vehicle in vehicles:
        with get_session(ji_engine) as session:
            vehicle = session.get(Vehicle, vehicle.id)
            if vehicle is None:
                continue
            result = resolve_vehicle(vehicle, session, pi_engine, rules, dry_run)
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
