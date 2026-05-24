"""
Re-runs the resolution pipeline on vehicles with unresolved/rule_applied/no_match discrepancies.
Triggered after new MappingRules are approved.

CLI:
  python -m pipeline.reprocess_job [--dry-run]
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from junkyard_common.db import get_engine, get_session
from junkyard_common.models import MappingDiscrepancy, MappingRule, Vehicle
from pipeline.resolution_pipeline import resolve_vehicle

REPROCESS_STATUSES = ("unresolved", "rule_applied", "no_match_in_dataset")


def get_reprocess_vehicle_ids(session: Session) -> list[int]:
    """Return vehicle IDs whose discrepancy status is eligible for reprocessing."""
    rows = session.execute(
        select(MappingDiscrepancy.vehicle_id)
        .where(MappingDiscrepancy.status.in_(REPROCESS_STATUSES))
        .order_by(MappingDiscrepancy.vehicle_id)
    ).scalars().all()
    return list(rows)


def reprocess_vehicle(
    vehicle: Vehicle,
    session: Session,
    pi_engine,
    rules: list[MappingRule],
    dry_run: bool,
) -> str:
    """Reset car_id fields and re-run resolution pipeline."""
    vehicle.car_id = None
    vehicle.car_id_resolved = False
    vehicle.car_id_method = None
    vehicle.car_id_confidence = None
    return resolve_vehicle(vehicle, session, pi_engine, rules, dry_run)


def run_reprocess(dry_run: bool = False) -> None:
    ji_engine = get_engine()
    pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"])

    with get_session(ji_engine) as session:
        vehicle_ids = get_reprocess_vehicle_ids(session)
        rules = session.execute(
            select(MappingRule)
            .where(MappingRule.is_active == True)  # noqa: E712
            .order_by(MappingRule.scope, MappingRule.priority)
        ).scalars().all()

    print(f"Reprocessing {len(vehicle_ids)} vehicles...")
    counts: dict[str, int] = {}

    for vid in vehicle_ids:
        with get_session(ji_engine) as session:
            vehicle = session.get(Vehicle, vid)
            if vehicle is None:
                continue
            result = reprocess_vehicle(vehicle, session, pi_engine, rules, dry_run)
            counts[result] = counts.get(result, 0) + 1

        processed = sum(counts.values())
        if processed % 100 == 0:
            print(f"Reprocessed {processed}: {counts}")

    print(f"Done. Final counts: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-run mapping pipeline on unresolved vehicles")
    parser.add_argument("--dry-run", action="store_true", help="Read-only, no DB writes")
    args = parser.parse_args()
    run_reprocess(dry_run=args.dry_run)
