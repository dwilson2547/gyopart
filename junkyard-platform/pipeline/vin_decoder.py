import time
from datetime import datetime, timezone

import requests
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import VinCache

_BATCH_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
_BATCH_SIZE = 50
_BATCH_SLEEP = 0.5


def _fetch_nhtsa_batch(vins: list[str]) -> list[dict]:
    """POST up to 50 VINs to the NHTSA batch endpoint. Returns flat result dicts."""
    resp = requests.post(
        _BATCH_URL,
        data={"DATA": ";".join(vins), "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("Results", [])


def _cache_row(r: dict, now: datetime) -> VinCache | None:
    """VinCache row for one NHTSA result, keeping the full record in `raw`."""
    vin = (r.get("VIN") or "").strip().upper()
    if not vin:
        return None
    error_code = r.get("ErrorCode") or ""
    make = r.get("Make") or ""
    model_year = r.get("ModelYear") or ""
    if "11" in error_code or not make or not model_year:
        return VinCache(vin=vin, error_code=error_code or "INCOMPLETE", raw=r, fetched_at=now)
    return VinCache(vin=vin, make=make, model=r.get("Model") or "", model_year=model_year,
                    trim=r.get("Trim") or "", error_code=None, raw=r, fetched_at=now)


def _decoded(row: VinCache) -> dict | None:
    if row.error_code:
        return None
    return {"make": row.make, "model": row.model, "model_year": row.model_year, "trim": row.trim,
            "raw": row.raw or {}}


def fetch_into_cache(vins: list[str], session: Session) -> dict[str, dict | None]:
    """Decode VINs cache-first, fetching misses in NHTSA batches; returns vin -> decode (None = undecodable).

    A cached row without `raw` (written before the full record was kept) counts as a miss, so it is
    re-fetched once and upgraded. Caller commits.
    """
    valid = sorted({v.strip().upper() for v in vins if v and len(v.strip()) == 17})
    out: dict[str, dict | None] = {}
    if not valid:
        return out
    cached = {r.vin: r for r in session.execute(select(VinCache).where(VinCache.vin.in_(valid))).scalars()}
    misses = [v for v in valid if v not in cached or cached[v].raw is None]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(0, len(misses), _BATCH_SIZE):
        for r in _fetch_nhtsa_batch(misses[i:i + _BATCH_SIZE]):
            row = _cache_row(r, now)
            if row is not None:
                cached[row.vin] = session.merge(row)
        if i + _BATCH_SIZE < len(misses):
            time.sleep(_BATCH_SLEEP)
    for v in valid:
        out[v] = _decoded(cached[v]) if v in cached else None
    return out


def warm_vin_cache_bulk(vins: list[str], engine: Engine) -> dict[str, int]:
    """Pre-populate VinCache with the batch endpoint before a per-vehicle loop (batch CLI path)."""
    with Session(engine) as s:
        decoded = fetch_into_cache(vins, s)
        s.commit()
    counts = {"decoded": sum(1 for d in decoded.values() if d), "error": sum(1 for d in decoded.values() if not d)}
    print(f"VIN cache warm-up: {counts}")
    return counts


def decode_vin(vin: str, session: Session) -> dict | None:
    """Cache-first NHTSA VIN decode. Returns None for invalid/pre-1980 VINs."""
    if not vin or len(vin) != 17:
        return None
    vin = vin.upper()
    cached = session.get(VinCache, vin)
    if cached is not None and cached.raw is not None:
        return _decoded(cached)

    time.sleep(1)
    try:
        results = _fetch_nhtsa_batch([vin])
    except Exception:
        return None
    row = _cache_row(results[0], datetime.now(timezone.utc).replace(tzinfo=None)) if results else None
    if row is None:
        return None
    row = session.merge(row)
    session.commit()
    return _decoded(row)
