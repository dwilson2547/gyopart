#!/usr/bin/env python3
# Site:     Wrench A Part (https://wrenchapart.com)
# API:      https://api.wrenchapart.com — custom REST API, no auth required
# Strategy: GET /locations → seed Location rows; GET /v1/vehicles → full flat JSON array → upsert
# Dedup key: VIN (stored as source_key); stock_number + GPS row coords → extras
# Source identifier: "wrenchapart"

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

API_BASE                = "https://api.wrenchapart.com"
DOMAIN                  = "api.wrenchapart.com"
SOURCE                  = "wrenchapart"
CLIENT_NAME             = "wrenchapart"

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

    logger.info("GET %s", url)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.json()


def _ensure_locations(
    db: Session,
    locations_data: list[dict],
    now: datetime,
) -> dict[int, int]:
    """Upsert location rows from the /locations API response. Returns {yard_id: location_id}."""
    location_ids: dict[int, int] = {}
    for loc in locations_data:
        yard_id = loc.get("id")
        if yard_id is None:
            continue
        source_location_id = str(yard_id)
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_location_id).first()
        name = loc.get("name") or f"Wrench A Part #{yard_id}"
        # API field names vary; try several common patterns
        address = loc.get("street") or loc.get("address") or loc.get("streetAddress")
        city    = loc.get("city")
        state   = loc.get("state") or "TX"
        zip_code = loc.get("zip") or loc.get("zipCode") or loc.get("postalCode")
        phone   = loc.get("phone") or loc.get("phoneNumber")

        if obj is None:
            obj = Location(
                source=SOURCE,
                source_location_id=source_location_id,
                name=f"Wrench A Part — {name}",
                address=address,
                city=city,
                state=state,
                zip_code=zip_code,
                phone=phone,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.name = f"Wrench A Part — {name}"
            obj.address = address
            obj.city = city
            obj.phone = phone
            obj.last_seen_at = now
            db.commit()

        location_ids[yard_id] = obj.id

    return location_ids


def _parse_vehicle(record: dict, location_ids: dict[int, int]) -> dict | None:
    vin = (record.get("vin") or "").strip()
    if not vin or len(vin) != 17:
        return None

    yard_id = record.get("yard")
    location_id = location_ids.get(yard_id)
    if location_id is None:
        logger.warning("Unknown yard ID %s — skipping VIN %s", yard_id, vin)
        return None

    row_obj = record.get("row") or {}
    row_str = str(row_obj.get("id")) if row_obj.get("id") is not None else None

    extras: dict = {}
    if stock := record.get("stockNumber"):
        extras["stock_number"] = stock
    lat = row_obj.get("latitude")
    lng = row_obj.get("longitude")
    if lat and lng:
        try:
            extras["row_lat"] = float(lat)
            extras["row_lng"] = float(lng)
        except (TypeError, ValueError):
            pass

    return {
        "vin":               vin,
        "location_id":       location_id,
        "year":              record.get("modelYear"),
        "make":              (record.get("make") or {}).get("name"),
        "model":             (record.get("model") or {}).get("name"),
        "color":             record.get("color") or None,
        "row":               row_str,
        "arrival_date":      _parse_arrival_date(record.get("dateAdded")),
        "preview_image_url": record.get("photo") or None,
        "extras":            extras or None,
    }


def _upsert_vehicles(
    db: Session,
    vehicles: list[dict],
    now: datetime,
) -> tuple[int, int, int]:
    current_vins = {v["vin"] for v in vehicles}

    existing_vins: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_vins))
        .all()
    }

    new_count = updated_count = 0
    for data in vehicles:
        vin = data["vin"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=data["location_id"],
                source=SOURCE,
                source_key=vin,
                vin=vin,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                row=data.get("row"),
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
                    "location_id":       data["location_id"],
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "color":             data.get("color"),
                    "row":               data.get("row"),
                    "arrival_date":      data.get("arrival_date"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
                    "last_seen_at":      now,
                    "is_active":         True,
                },
            )
        )
        db.execute(stmt)
        if vin in existing_vins:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(
            Vehicle.source == SOURCE,
            Vehicle.is_active.is_(True),
            ~Vehicle.source_key.in_(current_vins),
        )
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        run = ScrapeRun(source=SOURCE, location_id=None, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            locations_data = _fetch_json(http, web_cache, request_auth, f"{API_BASE}/locations")
            with Session(engine) as db:
                location_ids = _ensure_locations(db, locations_data, now)
            logger.info("Locations seeded: %d yards", len(location_ids))

            records = _fetch_json(http, web_cache, request_auth, f"{API_BASE}/v1/vehicles")
            logger.info("Fetched %d vehicle records", len(records))

        vehicles, skipped = [], 0
        for record in records:
            parsed = _parse_vehicle(record, location_ids)
            if parsed:
                vehicles.append(parsed)
            else:
                skipped += 1
        if skipped:
            logger.info("Skipped %d records (no VIN or unknown yard)", skipped)

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(db, vehicles, now)

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total=%d",
            new_c, updated_c, removed_c, len(vehicles),
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(vehicles)
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
