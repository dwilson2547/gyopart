#!/usr/bin/env python3
# Site:     Pick-n-Pull (https://www.picknpull.com/)
# Strategy: ajax-api (public JSON endpoints, no browser required)
# Dedup key: vehicle.id stored as source_key.
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)
# Source identifier: "pic_n_pull"

import json
import logging
import sys
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE = Config.SOURCE
DOMAIN = "www.picknpull.com"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except (ValueError, TypeError):
        return None


def _get_json(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
    params: dict | None = None,
) -> list | dict:
    req = requests.Request("GET", url, params=params).prepare()
    cache_key = req.url
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=Config.HEADERS, params=params, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _sync_locations(http, web_cache, request_auth, db, now) -> list[dict]:
    logger.info("Syncing locations …")
    locations: list[dict] = _get_json(http, web_cache, request_auth, Config.LOCATIONS_URL)
    api_ids: set[str] = {str(loc["id"]) for loc in locations}

    for loc in locations:
        source_loc_id = str(loc["id"])
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
        if obj is None:
            db.add(Location(
                source=SOURCE,
                source_location_id=source_loc_id,
                name=loc.get("listText") or f"{loc.get('city')}, {loc.get('state')}",
                chain=Config.CHAIN,
                city=loc.get("city"),
                state=loc.get("state"),
                zip_code=loc.get("postalCode"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            ))
        else:
            obj.last_seen_at = now
            obj.is_active = True

    db.query(Location).filter(
        Location.source == SOURCE,
        Location.is_active.is_(True),
        ~Location.source_location_id.in_(api_ids),
    ).update({"is_active": False}, synchronize_session="fetch")

    db.commit()
    logger.info("Locations synced: %d active.", len(locations))
    return locations


def _sync_location_inventory(http, web_cache, request_auth, db, api_loc, now):
    zip_code = api_loc["postalCode"]
    source_loc_id = str(api_loc["id"])
    loc_name = api_loc.get("listText", zip_code)

    logger.info("Fetching vehicles for %s (id=%s, zip=%s) …", loc_name, source_loc_id, zip_code)

    results: list[dict] = _get_json(
        http, web_cache, request_auth, Config.VEHICLE_SEARCH_URL,
        params={"zip": zip_code, "distance": Config.SEARCH_DISTANCE_MILES,
                "makeId": "", "modelId": "", "year": ""},
    )

    matched = next(
        (r for r in results if str(r.get("location", {}).get("locationID", "")) == source_loc_id),
        None,
    )
    if matched is None:
        logger.warning("No vehicle-search result for location %s — skipping.", source_loc_id)
        return 0, 0, 0, 0

    api_location_data: dict = matched["location"]
    vehicles: list[dict] = matched.get("vehicles", [])

    loc_obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
    if loc_obj is None:
        logger.error("Location %s not in DB — skipping.", source_loc_id)
        return 0, 0, 0, 0

    if not loc_obj.address:
        loc_obj.address = api_location_data.get("address1") or api_location_data.get("address2")
    if not loc_obj.phone:
        loc_obj.phone = api_location_data.get("publicPhone1")
    if loc_obj.lat is None:
        loc_obj.lat = api_location_data.get("mapLatitude")
    if loc_obj.lng is None:
        loc_obj.lng = api_location_data.get("mapLongitude")
    full_name = api_location_data.get("name", "")
    if full_name and not loc_obj.name.startswith("Pick-n-Pull"):
        loc_obj.name = full_name

    location_db_id: int = loc_obj.id

    existing_vehicles: dict[str, Vehicle] = {
        v.source_key: v
        for v in db.query(Vehicle).filter_by(source=SOURCE, location_id=location_db_id).all()
    }

    current_source_keys: set[str] = set()
    new_count = updated_count = 0

    for v in vehicles:
        source_key = str(v["id"])
        current_source_keys.add(source_key)
        arrival_date = _parse_dt(v.get("dateAdded"))
        image_url: str | None = v.get("imageName") or v.get("smallImage") or None
        existing = existing_vehicles.get(source_key)

        if existing is None:
            db.add(Vehicle(
                location_id=location_db_id,
                source=SOURCE,
                source_key=source_key,
                year=v.get("year"),
                make=v.get("make"),
                model=v.get("model"),
                vin=v.get("vin") or None,
                row=v.get("row"),
                arrival_date=arrival_date,
                color=v.get("color") or None,
                trim=v.get("trim") or None,
                preview_image_url=image_url,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            ))
            new_count += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            if v.get("row"):
                existing.row = v["row"]
            if image_url and existing.preview_image_url != image_url:
                existing.preview_image_url = image_url
            updated_count += 1

    removed_count = 0
    for source_key, vehicle in existing_vehicles.items():
        if source_key not in current_source_keys and vehicle.is_active:
            vehicle.is_active = False
            removed_count += 1

    db.commit()
    logger.info("  %s: %d in feed  +%d new  ~%d updated  -%d removed",
                loc_name, len(vehicles), new_count, updated_count, removed_count)
    return len(vehicles), new_count, updated_count, removed_count


def main() -> None:
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        run = ScrapeRun(source=SOURCE, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache:
                request_auth = RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL)
                http = requests.Session()

                api_locations = _sync_locations(http, web_cache, request_auth, db, now)

                total_feed = total_new = total_updated = total_removed = 0
                for api_loc in api_locations:
                    feed, new, updated, removed = _sync_location_inventory(
                        http, web_cache, request_auth, db, api_loc, now
                    )
                    total_feed += feed
                    total_new += new
                    total_updated += updated
                    total_removed += removed

            run.completed_at = _utcnow()
            run.total_in_feed = total_feed
            run.new_vehicles = total_new
            run.updated_vehicles = total_updated
            run.removed_vehicles = total_removed
            run.success = True
            db.commit()
            logger.info("Scrape complete — %d locations | %d in feed | +%d new | ~%d updated | -%d removed",
                        len(api_locations), total_feed, total_new, total_updated, total_removed)

        except Exception as exc:
            logger.exception("Scrape failed: %s", exc)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
            sys.exit(1)


if __name__ == "__main__":
    main()
