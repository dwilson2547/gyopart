#!/usr/bin/env python3
# Site:     Utah Pic-A-Part (https://utpap.com)
# Platform: CrushYMS — unauthenticated XML feeds via SaaS config leak
# Strategy: GET two XML feeds (Orem + Ogden) → parse <ASSET> elements → upsert
# Feed URLs discovered via: GET .../api/admin/yard-config/utah_pic_a_part
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "utpap"

import logging
import os
import xml.etree.ElementTree as ET
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

DOMAIN                  = "45.79.157.162"
SOURCE                  = "utpap"
CLIENT_NAME             = "utpap"

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Feed URLs from CrushYMS config leak (client IDs 1065=Orem, 1064=Ogden).
# Plain HTTP intentional — server does not serve HTTPS on this IP.
_FEED_DEFS = {
    "orem": {
        "feed_url":           "http://45.79.157.162/1065_inventory.xml",
        "photo_prefix":       "https://utpap.com/Orem-inventory-photos",
        "source_location_id": "orem",
        "name":     "Utah Pic-A-Part — Orem, UT",
        "address":  "255 S. Geneva Road, Orem, UT 84058",
        "city":     "Orem",
        "state":    "UT",
        "zip_code": "84058",
        "phone":    "(801) 756-5878",
    },
    "ogden": {
        "feed_url":           "http://45.79.157.162/1064_inventory.xml",
        "photo_prefix":       "https://utpap.com/Ogden-inventory-photos",
        "source_location_id": "ogden",
        "name":     "Utah Pic-A-Part — Ogden, UT",
        "address":  "555 W. 17th Street, Ogden, UT 84404",
        "city":     "Ogden",
        "state":    "UT",
        "zip_code": "84404",
        "phone":    "(801) 612-6446",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_mileage(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # Format: 2026-05-18T11:20:00.677 (ISO 8601 with milliseconds)
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError:
        return None


def _fetch_text(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
) -> str:
    entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.info("GET %s", url)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.text


def _parse_feed(xml_text: str, photo_prefix: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    vehicles, skipped = [], 0
    for asset in root.findall("ASSET"):
        if asset.findtext("iSTATUS") != "0":
            skipped += 1
            continue

        vin = (asset.findtext("VIN") or "").strip()
        if not vin or len(vin) != 17:
            skipped += 1
            continue

        stock = (asset.findtext("STOCKNUMBER") or "").strip() or None
        preview_image_url = f"{photo_prefix}/{stock}.jpeg" if stock else None

        vehicles.append({
            "vin":               vin,
            "stock":             stock,
            "year":              _parse_year(asset.findtext("iYEAR")),
            "make":              (asset.findtext("MAKE") or "").strip() or None,
            "model":             (asset.findtext("MODEL") or "").strip() or None,
            "color":             (asset.findtext("COLOR") or "").strip() or None,
            "mileage":           _parse_mileage(asset.findtext("MILEAGE")),
            "row":               (asset.findtext("VEHICLE_ROW") or "").strip() or None,
            "arrival_date":      _parse_arrival_date(asset.findtext("YARD_IN_DATE")),
            "preview_image_url": preview_image_url,
        })

    if skipped:
        logger.debug("Skipped %d assets (non-active or no VIN)", skipped)
    return vehicles


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for slug, defn in _FEED_DEFS.items():
        loc_id = defn["source_location_id"]
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=loc_id).first()
        if obj is None:
            obj = Location(
                source=SOURCE,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
                source_location_id=loc_id,
                name=defn["name"],
                address=defn["address"],
                city=defn["city"],
                state=defn["state"],
                zip_code=defn["zip_code"],
                phone=defn["phone"],
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        location_ids[slug] = obj.id
    return location_ids


def _upsert_vehicles(
    db: Session,
    location_ids: dict[str, int],
    vehicles_by_location: dict[str, list[dict]],
    now: datetime,
) -> tuple[int, int, int]:
    all_vehicles = [v for vlist in vehicles_by_location.values() for v in vlist]
    current_vins = {v["vin"] for v in all_vehicles}

    existing_vins: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_vins))
        .all()
    }

    new_count = updated_count = 0
    for slug, vehicles in vehicles_by_location.items():
        location_id = location_ids[slug]
        for data in vehicles:
            vin = data["vin"]
            extras = {"stock_number": data["stock"]} if data.get("stock") else None
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
                    mileage=data.get("mileage"),
                    row=data.get("row"),
                    arrival_date=data.get("arrival_date"),
                    preview_image_url=data.get("preview_image_url"),
                    extras=extras,
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
                        "mileage":           data.get("mileage"),
                        "row":               data.get("row"),
                        "arrival_date":      data.get("arrival_date"),
                        "preview_image_url": data.get("preview_image_url"),
                        "extras":            extras,
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
        location_ids = _ensure_locations(db, now)
        run = ScrapeRun(source=SOURCE, location_id=None, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        vehicles_by_location: dict[str, list[dict]] = {}
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            for slug, defn in _FEED_DEFS.items():
                xml_text = _fetch_text(http, web_cache, request_auth, defn["feed_url"])
                parsed = _parse_feed(xml_text, defn["photo_prefix"])
                vehicles_by_location[slug] = parsed
                logger.info("  %s: %d vehicles", slug, len(parsed))

        total = sum(len(v) for v in vehicles_by_location.values())
        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(
                db, location_ids, vehicles_by_location, now
            )

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
