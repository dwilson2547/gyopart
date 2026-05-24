#!/usr/bin/env python3
# Site:     U-Pull and Save (https://www.u-pullandsave.com)
# Platform: Nuxt.js SPA, unauthenticated public REST API
# Strategy: year/make/model matrix → search all combos → detail fetch for new vehicleIDs only
# Dedup key: VIN (stored as source_key); extras["vehicle_id"] used for deactivation
# Source identifier: "u_pull_n_save"

import logging
import os
from datetime import datetime, timezone

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE                = "https://www.u-pullandsave.com"
DOMAIN                  = "u-pullandsave.com"
SOURCE                  = "u_pull_n_save"
CLIENT_NAME             = "u_pull_n_save"
STORE_ID                = 105
YEAR_MIN                = 1985

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _fetch_json(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
) -> list | dict:
    entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        import json
        return json.loads(entry["content"])

    logger.debug("GET %s", url)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.json()


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="105").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="105",
            name="U-Pull and Save — Pontiac, MI",
            address="625 South Opdyke Road, Pontiac, MI 48341",
            city="Pontiac",
            state="MI",
            zip_code="48341",
            phone="(248) 334-4111",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def _get_known_vehicle_ids(db: Session) -> dict[int, str]:
    """Returns {vehicle_id: source_key/VIN} for all active source vehicles."""
    rows = (
        db.query(Vehicle.source_key, Vehicle.extras)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True))
        .all()
    )
    result = {}
    for source_key, extras in rows:
        if extras and "vehicle_id" in extras:
            result[int(extras["vehicle_id"])] = source_key
    return result


def _fetch_recent_ids(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> set[int]:
    data = _fetch_json(http, web_cache, request_auth, f"{API_BASE}/api/vehicles/recent/{STORE_ID}")
    return {int(r["vehicleID"]) for r in data if r.get("vehicleID")}


def _collect_all_vehicle_ids(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> set[int]:
    """Build year/make/model matrix and search all combos. Returns all vehicleIDs in yard."""
    year_max = _utcnow().year + 2
    vehicle_ids: set[int] = set()
    total_combos = 0

    for year in range(YEAR_MIN, year_max):
        makes_data = _fetch_json(http, web_cache, request_auth, f"{API_BASE}/api/vehicles/make/{year}")
        for make_obj in makes_data:
            make = (make_obj.get("vehicleMake") or "").strip()
            if not make:
                continue
            models_data = _fetch_json(http, web_cache, request_auth, f"{API_BASE}/api/vehicles/model/{year}/{make}")
            for model_obj in models_data:
                model = (model_obj.get("trueModel") or "").strip()
                if not model:
                    continue
                total_combos += 1
                url = (
                    f"{API_BASE}/api/vehicles/search/"
                    f"?store={STORE_ID}&year={year}&make={make}&model={model}"
                )
                results = _fetch_json(http, web_cache, request_auth, url)
                for r in results:
                    vid = r.get("vehicleID")
                    if vid:
                        vehicle_ids.add(int(vid))

    logger.info("Matrix: %d combos → %d unique vehicleIDs", total_combos, len(vehicle_ids))
    return vehicle_ids


def _fetch_detail(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    vehicle_id: int,
) -> dict | None:
    url = f"{API_BASE}/api/vehicles/{vehicle_id}"
    try:
        data = _fetch_json(http, web_cache, request_auth, url)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("Detail fetch failed for vehicleID %d: %s", vehicle_id, exc)
        return None


def _parse_detail(detail: dict) -> dict | None:
    vin = (detail.get("VIN") or "").strip()
    if not vin or len(vin) != 17:
        return None

    vehicle_id = detail.get("vehicleID")
    stock_id = (detail.get("stockID") or "").strip() or None

    images = detail.get("images") or []
    preview_image_url = images[0].get("imageMedium") if images else None

    row_raw = detail.get("YardRow")
    row = str(row_raw) if row_raw is not None else None

    odometer = detail.get("odometerReading") or 0
    mileage = int(odometer) if odometer and int(odometer) > 0 else None

    extras: dict = {"vehicle_id": vehicle_id}
    if stock_id:
        extras["stock_number"] = stock_id

    return {
        "vin":               vin,
        "vehicle_id":        vehicle_id,
        "year":              detail.get("modelYear"),
        "make":              (detail.get("vehicleMake") or "").strip() or None,
        "model":             (detail.get("modelName") or "").strip() or None,
        "color":             (detail.get("colorOfVehicle") or "").strip() or None,
        "row":               row,
        "mileage":           mileage,
        "arrival_date":      _parse_arrival_date(detail.get("YardLocationDT")),
        "preview_image_url": preview_image_url,
        "extras":            extras,
    }


def _upsert_new_vehicles(
    db: Session,
    location_id: int,
    vehicles: list[dict],
    now: datetime,
    known_vins: set[str],
) -> tuple[int, int]:
    new_count = updated_count = 0
    for data in vehicles:
        vin = data["vin"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=vin,
                vin=vin,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                row=data.get("row"),
                mileage=data.get("mileage"),
                arrival_date=data.get("arrival_date"),
                preview_image_url=data.get("preview_image_url"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "location_id":       location_id,
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "color":             data.get("color"),
                    "row":               data.get("row"),
                    "mileage":           data.get("mileage"),
                    "arrival_date":      data.get("arrival_date"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
                    "last_seen_at":      now,
                    "is_active":         True,
                },
            )
        )
        db.execute(stmt)
        if vin in known_vins:
            updated_count += 1
        else:
            new_count += 1
    db.commit()
    return new_count, updated_count


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        location_id = _ensure_location(db, now)
        known_vehicle_ids = _get_known_vehicle_ids(db)
        known_vins: set[str] = set(known_vehicle_ids.values())
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            # Fast path: if all recent vehicleIDs are already known, skip full crawl
            recent_ids = _fetch_recent_ids(http, web_cache, request_auth)
            if recent_ids and recent_ids.issubset(known_vehicle_ids):
                logger.info(
                    "All %d recent vehicleIDs already known — skipping full crawl",
                    len(recent_ids),
                )
                with Session(engine) as db:
                    run = db.get(ScrapeRun, run_id)
                    run.completed_at = _utcnow()
                    run.total_in_feed = len(known_vehicle_ids)
                    run.new_vehicles = 0
                    run.updated_vehicles = 0
                    run.removed_vehicles = 0
                    run.success = True
                    db.commit()
                return

            # Full crawl: collect all vehicleIDs across year/make/model matrix
            current_vehicle_ids = _collect_all_vehicle_ids(http, web_cache, request_auth)

            # Fetch detail only for vehicleIDs not already in DB
            new_vehicle_ids = current_vehicle_ids - set(known_vehicle_ids)
            logger.info(
                "vehicleIDs — total=%d  new=%d  existing=%d",
                len(current_vehicle_ids), len(new_vehicle_ids),
                len(current_vehicle_ids) - len(new_vehicle_ids),
            )

            parsed_vehicles = []
            detail_errors = 0
            for vehicle_id in sorted(new_vehicle_ids):
                detail = _fetch_detail(http, web_cache, request_auth, vehicle_id)
                if detail is None:
                    detail_errors += 1
                    continue
                parsed = _parse_detail(detail)
                if parsed is None:
                    detail_errors += 1
                    continue
                parsed_vehicles.append(parsed)

            if detail_errors:
                logger.warning("Detail fetch/parse failures: %d", detail_errors)

        with Session(engine) as db:
            new_c, updated_c = _upsert_new_vehicles(
                db, location_id, parsed_vehicles, now, known_vins
            )

            # Mark still-present existing vehicles as seen
            still_present_ids = current_vehicle_ids & set(known_vehicle_ids)
            if still_present_ids:
                db.query(Vehicle).filter(
                    Vehicle.source == SOURCE,
                    Vehicle.extras["vehicle_id"].astext.in_(
                        [str(v) for v in still_present_ids]
                    ),
                ).update({"last_seen_at": now, "is_active": True}, synchronize_session="fetch")
                db.commit()

            # Deactivate vehicles no longer in yard
            removed_c = (
                db.query(Vehicle)
                .filter(
                    Vehicle.source == SOURCE,
                    Vehicle.is_active.is_(True),
                    ~Vehicle.extras["vehicle_id"].astext.in_(
                        [str(v) for v in current_vehicle_ids]
                    ),
                )
                .update({"is_active": False}, synchronize_session="fetch")
            )
            db.commit()

        total = len(current_vehicle_ids)
        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total=%d",
            new_c, updated_c, removed_c, total,
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = total
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

    except SystemExit:
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = "429 rate limit — permanent backoff"
            run.success = False
            db.commit()
        raise

    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
        raise

    finally:
        request_auth.close()


if __name__ == "__main__":
    main()
