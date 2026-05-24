import time
from datetime import datetime, timezone

import requests
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import VinCache
from pipeline.pi_schema import (
    pi_car_table, pi_make_table, pi_model_table, pi_year_table,
)

_SINGLE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
_BATCH_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
_BATCH_SIZE = 50
_BATCH_SLEEP = 0.5


def _fetch_nhtsa(vin: str) -> dict:
    resp = requests.get(_SINGLE_URL.format(vin=vin), timeout=15)
    resp.raise_for_status()
    return {r["Variable"]: r["Value"] for r in resp.json()["Results"]}


def _fetch_nhtsa_batch(vins: list[str]) -> list[dict]:
    """POST up to 50 VINs to the NHTSA batch endpoint. Returns flat result dicts."""
    resp = requests.post(
        _BATCH_URL,
        data={"DATA": ";".join(vins), "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("Results", [])


def warm_vin_cache_bulk(vins: list[str], engine: Engine) -> dict[str, int]:
    """
    Pre-populate VinCache using the NHTSA batch endpoint (50 VINs per request).

    Must be called before the per-vehicle pipeline loop so that all subsequent
    decode_vin() calls are guaranteed cache hits, eliminating per-VIN sleeps.
    Skips VINs that are already cached. Returns counts dict with keys
    'already_cached', 'stored', 'error', 'failed'.
    """
    valid = list({v for v in vins if v and len(v) == 17})
    if not valid:
        return {}

    with Session(engine) as s:
        cached = set(
            s.execute(select(VinCache.vin).where(VinCache.vin.in_(valid))).scalars()
        )
    uncached = [v for v in valid if v not in cached]

    counts: dict[str, int] = {"already_cached": len(cached), "stored": 0, "error": 0, "failed": 0}

    if not uncached:
        print(f"Bulk warm-up: all {len(valid)} VINs already cached.")
        return counts

    n_batches = (len(uncached) + _BATCH_SIZE - 1) // _BATCH_SIZE
    print(f"Bulk warm-up: {len(cached)} cached, {len(uncached)} to fetch in {n_batches} batch(es).")

    now = datetime.now(timezone.utc)

    for i in range(0, len(uncached), _BATCH_SIZE):
        chunk = uncached[i : i + _BATCH_SIZE]
        try:
            results = _fetch_nhtsa_batch(chunk)
        except Exception as e:
            print(f"  Batch {i // _BATCH_SIZE + 1} failed: {e}")
            counts["failed"] += len(chunk)
            time.sleep(_BATCH_SLEEP)
            continue

        rows = []
        for r in results:
            vin = (r.get("VIN") or "").strip()
            if not vin:
                continue
            error_code = r.get("ErrorCode") or ""
            make = r.get("Make") or ""
            model_year = r.get("ModelYear") or ""

            if "11" in error_code or not make or not model_year:
                rows.append(VinCache(vin=vin, error_code=error_code or "INCOMPLETE", fetched_at=now))
                counts["error"] += 1
            else:
                rows.append(VinCache(
                    vin=vin,
                    make=make,
                    model=r.get("Model") or "",
                    model_year=model_year,
                    trim=r.get("Trim") or "",
                    fetched_at=now,
                ))
                counts["stored"] += 1

        with Session(engine) as s:
            for row in rows:
                s.merge(row)
            s.commit()

        if i + _BATCH_SIZE < len(uncached):
            time.sleep(_BATCH_SLEEP)

    print(f"Bulk warm-up complete: {counts}")
    return counts


def decode_vin(vin: str, session: Session) -> dict | None:
    """Cache-first NHTSA VIN decode. Returns None for invalid/pre-1980 VINs."""
    if not vin or len(vin) != 17:
        return None

    cached = session.get(VinCache, vin)
    if cached is not None:
        if cached.error_code:
            return None
        return {
            "make": cached.make,
            "model": cached.model,
            "model_year": cached.model_year,
            "trim": cached.trim,
        }

    time.sleep(1)
    try:
        nhtsa = _fetch_nhtsa(vin)
    except Exception:
        return None

    error_code = nhtsa.get("ErrorCode") or ""
    make = nhtsa.get("Make") or ""
    model_year = nhtsa.get("ModelYear") or ""

    if "11" in error_code or not make or not model_year:
        session.merge(VinCache(
            vin=vin,
            error_code=error_code or "INCOMPLETE",
            fetched_at=datetime.now(timezone.utc),
        ))
        session.commit()
        return None

    result = {
        "make": make,
        "model": nhtsa.get("Model") or "",
        "model_year": model_year,
        "trim": nhtsa.get("Trim") or "",
    }
    session.merge(VinCache(vin=vin, fetched_at=datetime.now(timezone.utc), **result))
    session.commit()
    return result


def resolve_vin_to_car_id(decoded: dict, pi_engine: Engine) -> int | None:
    """Match decoded VIN year/make/model against parts_interchange.car. Returns car.id or None."""
    year_str = (decoded.get("model_year") or "").strip()
    make_str = (decoded.get("make") or "").strip()
    model_str = (decoded.get("model") or "").strip()

    if not (year_str and make_str and model_str):
        return None

    with pi_engine.connect() as conn:
        year_row = conn.execute(
            select(pi_year_table.c.id).where(pi_year_table.c.name == year_str)
        ).one_or_none()
        if not year_row:
            return None

        make_row = conn.execute(
            select(pi_make_table.c.id).where(
                text("lower(name) = lower(:name)")
            ).params(name=make_str)
        ).one_or_none()
        if not make_row:
            return None

        model_row = conn.execute(
            select(pi_model_table.c.id).where(
                pi_model_table.c.make_id == make_row[0],
                text("lower(name) = lower(:name)")
            ).params(name=model_str)
        ).one_or_none()
        if not model_row:
            return None

        car_row = conn.execute(
            select(pi_car_table.c.id).where(
                pi_car_table.c.year_id == year_row[0],
                pi_car_table.c.make_id == make_row[0],
                pi_car_table.c.model_id == model_row[0],
            )
        ).first()
        return car_row[0] if car_row else None
