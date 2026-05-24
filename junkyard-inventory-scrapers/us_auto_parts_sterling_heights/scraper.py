#!/usr/bin/env python3
# Site:     US Auto Supply — Sterling Heights, MI
# Strategy: XML feed (CrushYMS single-request XML inventory)
# Feed URL: http://45.79.157.162/1066_inventory.xml
# Dedup key: STOCKNUMBER stored as source_key
# Source identifier: "us_auto_supply"
# Extras JSONB: hol_model, reference, vehicle_row, location_string, last_update, status
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)

import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

XML_FEED_URL            = "http://45.79.157.162/1066_inventory.xml"
XML_FEED_DOMAIN         = urlparse(XML_FEED_URL).netloc
SOURCE                  = "us_auto_supply"
CLIENT_NAME             = "us_auto_supply_sterling_heights"
WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml, text/xml, */*",
}

# XML fields that map directly to canonical Vehicle columns
CANONICAL_FIELDS = {
    "VIN":          "vin",
    "iYEAR":        "year",
    "MAKE":         "make",
    "MODEL":        "model",
    "COLOR":        "color",
    "YARD_IN_DATE": "arrival_date",
    "MILEAGE":      "mileage",
}

# XML fields that go into extras JSONB (yard-specific)
EXTRAS_FIELDS = {
    "HOL_MODEL":   "hol_model",
    "REFERENCE":   "reference",
    "VEHICLE_ROW": "vehicle_row",
    "LOCATION":    "location_string",
    "LASTUPDATE":  "last_update",
    "iSTATUS":     "status",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.split(".")[0])
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_asset(asset_el) -> dict | None:
    stock_number = (asset_el.findtext("STOCKNUMBER") or "").strip() or None
    if not stock_number:
        return None

    canonical: dict = {"stock_number": stock_number}
    for xml_tag, field in CANONICAL_FIELDS.items():
        raw = (asset_el.findtext(xml_tag) or "").strip() or None
        if field == "year":
            canonical[field] = _parse_int(raw)
        elif field == "mileage":
            canonical[field] = _parse_int(raw)
        elif field == "arrival_date":
            canonical[field] = _parse_arrival_date(raw)
        else:
            canonical[field] = raw

    extras: dict = {}
    for xml_tag, key in EXTRAS_FIELDS.items():
        raw = (asset_el.findtext(xml_tag) or "").strip() or None
        if raw is not None:
            extras[key] = raw
    canonical["extras"] = extras or None

    return canonical


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="US Auto Supply — Sterling Heights",
            city="Sterling Heights",
            state="MI",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def fetch_xml(session, web_cache, request_auth) -> str:
    entry = web_cache.get(XML_FEED_URL, max_age=3600)
    if entry:
        logger.info("Cache hit for XML feed")
        return entry["content"]
    with request_auth.acquire(XML_FEED_DOMAIN) as permit:
        resp = session.get(XML_FEED_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    web_cache.store(XML_FEED_URL, resp.text, CLIENT_NAME)
    return resp.text


def upsert_vehicles(
    db: Session, location_id: int, assets: list[dict], now: datetime
) -> tuple[int, int, int]:
    current_stock_numbers = {d["stock_number"] for d in assets}

    existing_stocks: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_stock_numbers))
        .all()
    }

    new_count = updated_count = 0

    for data in assets:
        stock = data["stock_number"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=stock,
                vin=data.get("vin"),
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                arrival_date=data.get("arrival_date"),
                mileage=data.get("mileage"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "vin":          data.get("vin"),
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "color":        data.get("color"),
                    "arrival_date": data.get("arrival_date"),
                    "mileage":      data.get("mileage"),
                    "extras":       data.get("extras"),
                    "last_seen_at": now,
                    "is_active":    True,
                },
            )
        )
        db.execute(stmt)
        if stock in existing_stocks:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_stock_numbers))
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


def main() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
        location_id = _ensure_location(db, now)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            xml_text = fetch_xml(http, web_cache, request_auth)

        root = ET.fromstring(xml_text)
        all_assets, skipped = [], 0
        for asset_el in root.findall("ASSET"):
            parsed = _parse_asset(asset_el)
            if parsed:
                all_assets.append(parsed)
            else:
                skipped += 1

        logger.info("Parsed %d assets (%d skipped)", len(all_assets), skipped)

        with Session(engine) as db:
            new_c, updated_c, removed_c = upsert_vehicles(db, location_id, all_assets, now)

        logger.info("Run complete — new=%d  updated=%d  removed=%d  total_in_feed=%d",
                    new_c, updated_c, removed_c, len(all_assets))

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(all_assets)
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

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
