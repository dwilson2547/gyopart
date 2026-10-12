"""
Live VIN resolver: an always-on worker that uses the vehicles table as its queue.

A vehicle is queued while `car_id_resolved = false AND resolve_attempted_at IS NULL` (scrapers insert new
vehicles that way). Each pass claims up to 50 of them with FOR UPDATE SKIP LOCKED, decodes their VINs in one
NHTSA batch call (cache-first; vin_cache keeps the full record), resolves each to its candidate catalogue cars,
and commits. New yard vehicles resolve within seconds of being scraped; a backlog drains at one batch per pass.

Failures: an NHTSA/DB error rolls the batch back (vehicles stay queued) and backs off; a single vehicle that
raises is marked attempted so it cannot wedge the queue. Discrepancies stay out of the queue until a rule
change requeues them (reprocess_job).

CLI:
  python -m pipeline.worker                       # run forever
  python -m pipeline.worker --once                # drain the queue, then exit
  python -m pipeline.worker --requeue vin_decode  # put vehicles resolved by these methods back in the queue
  python -m pipeline.worker --requeue vin_exact vin_candidates ymmt_match rule_applied vin_decode discrepancy
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from junkyard_common.db import get_engine
from junkyard_common.models import MappingRule, Vehicle
from pipeline.resolution_pipeline import geocode_locations, resolve_vehicle
from pipeline.vin_decoder import fetch_into_cache

logger = logging.getLogger("vin_resolver")

BATCH_SIZE = 50  # NHTSA batch endpoint limit
IDLE_SLEEP_S = float(os.environ.get("RESOLVER_IDLE_SLEEP_S", "10"))
ERROR_SLEEP_S = float(os.environ.get("RESOLVER_ERROR_SLEEP_S", "60"))
GEOCODE_EVERY_S = float(os.environ.get("RESOLVER_GEOCODE_EVERY_S", "600"))

_stop = False


def _handle_stop(signum, _frame) -> None:
    global _stop
    logger.info("signal %s: finishing the current batch, then exiting", signum)
    _stop = True


def process_batch(ji_engine, pi_engine) -> dict[str, int]:
    """Claim, decode and resolve one batch. Returns outcome counts ({} = queue empty)."""
    counts: dict[str, int] = {}
    with Session(ji_engine) as session:
        vehicles = session.execute(
            select(Vehicle)
            .where(Vehicle.car_id_resolved == False, Vehicle.resolve_attempted_at.is_(None))  # noqa: E712
            .order_by(Vehicle.id)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        ).scalars().all()
        if not vehicles:
            return counts

        # Loaded per batch, in this session, so rule applied_count updates land with the batch.
        rules = session.execute(
            select(MappingRule).where(MappingRule.is_active == True)  # noqa: E712
            .order_by(MappingRule.scope, MappingRule.priority)
        ).scalars().all()
        decoded = fetch_into_cache([v.vin for v in vehicles if v.vin], session)
        for vehicle in vehicles:
            vin = (vehicle.vin or "").strip().upper()
            try:
                with session.begin_nested():
                    result = resolve_vehicle(vehicle, session, pi_engine, rules,
                                             decoded=decoded.get(vin), commit=False)
            except Exception:
                logger.exception("vehicle %s (%s): resolve failed; marking attempted", vehicle.id, vin or "no vin")
                vehicle.resolve_attempted_at = time_now()
                result = "error"
            counts[result] = counts.get(result, 0) + 1
        session.commit()
    return counts


def time_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def requeue(ji_engine, methods: list[str]) -> int:
    """Put vehicles back in the queue: those resolved by `methods`, plus unmatched ones if "discrepancy" is
    listed. Use after improving matching logic (decodes come from vin_cache, so NHTSA is not re-hit)."""
    cond = Vehicle.car_id_method.in_(methods)
    if "discrepancy" in methods:
        cond = cond | ((Vehicle.car_id_resolved == False) & Vehicle.resolve_attempted_at.isnot(None))  # noqa: E712
    with Session(ji_engine) as s:
        n = s.execute(
            update(Vehicle)
            .where(cond)
            .values(car_id_resolved=False, car_id=None, car_id_method=None, car_id_confidence=None,
                    car_id_candidates=None, resolve_attempted_at=None)
        ).rowcount
        s.commit()
    return n


def run(once: bool = False) -> None:
    ji_engine = get_engine()
    pi_engine = create_engine(os.environ["PARTS_DATABASE_URL"], pool_pre_ping=True)
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    geocoded_at = 0.0
    totals: dict[str, int] = {}
    logger.info("vin resolver started (batch %d, idle sleep %.0fs)", BATCH_SIZE, IDLE_SLEEP_S)
    while not _stop:
        now = time.monotonic()
        if now - geocoded_at >= GEOCODE_EVERY_S:
            try:
                geocode_locations(ji_engine)
            except Exception:
                logger.exception("geocoding failed; retrying next interval")
            geocoded_at = now

        try:
            counts = process_batch(ji_engine, pi_engine)
        except Exception:
            logger.exception("batch failed; vehicles stay queued, backing off %.0fs", ERROR_SLEEP_S)
            time.sleep(ERROR_SLEEP_S)
            continue

        if not counts:
            if once:
                break
            time.sleep(IDLE_SLEEP_S)
            continue
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
        logger.info("batch %s | totals %s", counts, totals)
    logger.info("vin resolver stopped; totals %s", totals)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Live VIN resolver worker")
    parser.add_argument("--once", action="store_true", help="drain the queue, then exit")
    parser.add_argument("--requeue", nargs="+", metavar="METHOD",
                        help="requeue vehicles resolved by these car_id_method values, then exit")
    args = parser.parse_args()
    if args.requeue:
        print(f"requeued {requeue(get_engine(), args.requeue)} vehicles")
    else:
        run(once=args.once)
