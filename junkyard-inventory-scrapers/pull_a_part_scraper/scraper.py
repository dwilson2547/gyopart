#!/usr/bin/env python3
# Site:     Pull-A-Part (https://www.pullapart.com/inventory/)
# Strategy: ajax-api (JSON endpoints, no browser required)
# Dedup key: source_key = f"{ticket_id}:{line_id}"
# Source identifier: "pull_a_part"
# Extras JSONB: vin_id, make_id, model_id, vin_decoded_id
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)
#
# Phases:
#   1. Sync locations (Location rows via enterprise API)
#   2. Fetch makes list (build make_lookup dict for Vehicle.make — not stored in DB)
#   3. Sync inventory (Vehicle rows; one POST per make across all locations)
#   4. Fetch details (flat Vehicle fields: trim/body_type/engine/etc.)

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE = Config.SOURCE


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:19])
    except (ValueError, TypeError):
        return None


def _cache_key_for_get(url: str, params: dict | None = None) -> str:
    req = requests.Request("GET", url, params=params).prepare()
    return req.url


def _cache_key_for_post(url: str, payload: dict) -> str:
    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{url}#body={payload_str}"


def _get(http, web_cache, request_auth, url, params=None):
    cache_key = _cache_key_for_get(url, params)
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    domain = urlparse(url).netloc
    with request_auth.acquire(domain) as permit:
        resp = http.get(url, headers=Config.HEADERS, params=params, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _post(http, web_cache, request_auth, url, payload):
    cache_key = _cache_key_for_post(url, payload)
    entry = web_cache.get(cache_key, max_age=Config.CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.debug("Cache hit: %s", cache_key)
        return json.loads(entry["content"])
    domain = urlparse(url).netloc
    with request_auth.acquire(domain) as permit:
        resp = http.post(url, json=payload, headers=Config.HEADERS, timeout=30)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(cache_key, resp.text, Config.CLIENT_NAME)
    return resp.json()


def _sync_locations(http, web_cache, request_auth, db, now) -> list[int]:
    """Upsert all PAP locations; return list of active API location IDs."""
    logger.info("Syncing locations …")
    data = _get(http, web_cache, request_auth, Config.LOCATIONS_URL, params=Config.LOCATIONS_PARAMS)

    api_ids: set[int] = set()
    for loc in data:
        loc_id = loc["locationID"]
        api_ids.add(loc_id)
        source_loc_id = str(loc_id)

        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=source_loc_id).first()
        if obj is None:
            db.add(Location(
                source=SOURCE,
                source_location_id=source_loc_id,
                name=loc.get("name") or loc.get("locationName") or loc.get("locName") or source_loc_id,
                chain=Config.CHAIN,
                address=loc.get("address"),
                city=loc.get("city"),
                state=loc.get("state"),
                zip_code=loc.get("zip") or loc.get("postalCode"),
                phone=loc.get("phone"),
                lat=loc.get("lat") or loc.get("latitude"),
                lng=loc.get("lng") or loc.get("longitude"),
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
        ~Location.source_location_id.in_([str(i) for i in api_ids]),
    ).update({"is_active": False}, synchronize_session="fetch")

    db.commit()
    active_ids = sorted(api_ids)
    logger.info("Locations synced: %d active.", len(active_ids))
    return active_ids


def _fetch_make_lookup(http, web_cache, request_auth) -> dict[int, str]:
    """Return {makeID: makeName} dict. Not stored in DB — used only for Vehicle.make lookup."""
    logger.info("Fetching makes …")
    data = _get(http, web_cache, request_auth, Config.MAKES_URL)
    lookup = {m["makeID"]: m.get("makeName", "") for m in data}
    logger.info("Makes fetched: %d.", len(lookup))
    return lookup


def _sync_inventory(http, web_cache, request_auth, db, location_ids, make_lookup, run) -> None:
    """Upsert inventory across all locations. One POST per make."""
    logger.info("Syncing inventory — %d makes × %d locations …", len(make_lookup), len(location_ids))
    now = _utcnow()

    location_db_ids: dict[int, int] = {
        int(loc.source_location_id): loc.id
        for loc in db.query(Location).filter(
            Location.source == SOURCE, Location.is_active.is_(True)
        ).all()
    }

    existing: dict[str, Vehicle] = {
        v.source_key: v
        for v in db.execute(select(Vehicle).where(Vehicle.source == SOURCE)).scalars().all()
    }

    seen_keys: set[str] = set()
    new_count = 0

    for i, (make_id, make_name) in enumerate(make_lookup.items(), 1):
        payload = {"Locations": location_ids, "MakeID": make_id, "Models": [], "Years": []}
        try:
            data = _post(http, web_cache, request_auth, Config.INVENTORY_URL, payload)
        except requests.HTTPError as exc:
            logger.warning("HTTP error fetching make %s: %s", make_id, exc)
            continue

        for loc_result in data:
            for v in loc_result.get("exact", []) + loc_result.get("other", []):
                ticket_id  = v["ticketID"]
                line_id    = v["lineID"]
                loc_id     = v["locID"]
                source_key = f"{ticket_id}:{line_id}"
                seen_keys.add(source_key)

                location_db_id = location_db_ids.get(loc_id)
                if location_db_id is None:
                    continue

                if source_key in existing:
                    existing[source_key].last_seen_at = now
                    existing[source_key].is_active = True
                else:
                    new_v = Vehicle(
                        location_id=location_db_id,
                        source=SOURCE,
                        source_key=source_key,
                        year=v.get("modelYear"),
                        make=make_name,
                        model=v.get("modelName"),
                        vin=v.get("vin") or None,
                        row=v.get("row"),
                        arrival_date=_parse_dt(v.get("dateYardOn")),
                        extras={
                            "vin_id":         v.get("vinID"),
                            "make_id":        make_id,
                            "model_id":       v.get("modelID"),
                            "vin_decoded_id": v.get("vinDecodedId"),
                        },
                        is_active=True,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    db.add(new_v)
                    existing[source_key] = new_v
                    new_count += 1

        db.commit()
        if i % 10 == 0:
            logger.info("  … %d/%d makes processed", i, len(make_lookup))

    removed_count = 0
    for source_key, vehicle in existing.items():
        if source_key not in seen_keys and vehicle.is_active:
            vehicle.is_active = False
            removed_count += 1

    db.commit()
    run.new_vehicles     = new_count
    run.removed_vehicles = removed_count
    db.commit()
    logger.info("Inventory sync complete — %d added, %d removed.", new_count, removed_count)


def _fetch_details(http, web_cache, request_auth, db, run) -> None:
    """Fetch VehicleExtendedInfo for new vehicles (detail_fetched_at IS NULL)."""
    vehicles = (
        db.execute(
            select(Vehicle).where(
                Vehicle.source == SOURCE,
                Vehicle.is_active.is_(True),
                Vehicle.detail_fetched_at.is_(None),
            )
        ).scalars().all()
    )

    if not vehicles:
        logger.info("No vehicles missing details — skipping detail phase.")
        return

    logger.info("Fetching details for %d new vehicles …", len(vehicles))
    fetched = 0
    now = _utcnow()

    for vehicle in vehicles:
        parts = vehicle.source_key.split(":")
        if len(parts) != 2:
            continue
        ticket_id, line_id = parts

        loc = db.get(Location, vehicle.location_id)
        loc_id = loc.source_location_id if loc else "0"

        url = Config.DETAILS_URL.format(loc_id=loc_id, ticket_id=ticket_id, line_id=line_id)
        try:
            data = _get(http, web_cache, request_auth, url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 404:
                vehicle.detail_fetched_at = now
                db.commit()
            else:
                logger.warning("HTTP %s fetching details for %s: %s", status, vehicle.source_key, exc)
            continue
        except Exception as exc:
            logger.warning("Error fetching details for %s: %s", vehicle.source_key, exc)
            continue

        vehicle.trim              = data.get("trim")
        vehicle.vehicle_type      = data.get("vehicleType")
        vehicle.body_type         = data.get("bodyType")
        vehicle.body_sub_type     = data.get("bodySubType")
        vehicle.doors             = data.get("doors")
        vehicle.drive_type        = data.get("driveType")
        vehicle.fuel_type         = data.get("fuelType")
        vehicle.engine_block      = data.get("engineBlock")
        vehicle.engine_cylinders  = data.get("engineCylinders")
        vehicle.engine_size       = data.get("engineSize")
        vehicle.engine_aspiration = data.get("engineAspiration")
        vehicle.trans_type        = data.get("transType")
        vehicle.trans_speeds      = data.get("transSpeeds")
        vehicle.style             = data.get("style")
        vehicle.color             = vehicle.color or data.get("color")
        vehicle.detail_fetched_at = now
        db.commit()

        fetched += 1
        if fetched % 100 == 0:
            logger.info("  … details fetched: %d/%d", fetched, len(vehicles))

    run.updated_vehicles = fetched
    db.commit()
    logger.info("Detail fetch complete — %d fetched.", fetched)


def main() -> None:
    engine = get_engine()
    http = requests.Session()
    request_auth = RequestAuthClient(Config.REQUEST_AUTH_SERVER_URL)
    now = _utcnow()

    with Session(engine) as db:
        run = ScrapeRun(source=SOURCE, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

        try:
            with WebCacheClient(Config.WEBCACHE_URL, timeout=Config.WEBCACHE_TIMEOUT) as web_cache:
                location_ids = _sync_locations(http, web_cache, request_auth, db, now)
                make_lookup  = _fetch_make_lookup(http, web_cache, request_auth)
                _sync_inventory(http, web_cache, request_auth, db, location_ids, make_lookup, run)
                _fetch_details(http, web_cache, request_auth, db, run)

            run.completed_at  = _utcnow()
            run.total_in_feed = (run.new_vehicles or 0) + (run.updated_vehicles or 0)
            run.success       = True
            db.commit()
            logger.info("Scrape run completed successfully.")

        except Exception as exc:
            logger.exception("Scraper failed: %s", exc)
            run.completed_at  = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success       = False
            db.commit()
            raise

        finally:
            request_auth.close()


if __name__ == "__main__":
    main()
