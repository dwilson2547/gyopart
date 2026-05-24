#!/usr/bin/env python3
# Site:     Tear-A-Part (https://tearapart.com)
# Platform: WordPress + tap-inventory-search-system plugin
# Strategy: extract WP nonce from /inventory/ → POST admin-ajax.php once per store
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "tear_a_part"

import logging
import os
import re
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

AJAX_URL                = "https://tearapart.com/wp-admin/admin-ajax.php"
INVENTORY_PAGE_URL      = "https://tearapart.com/inventory/"
DOMAIN                  = "tearapart.com"
SOURCE                  = "tear_a_part"
CLIENT_NAME             = "tear_a_part"

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

_NONCE_RE = re.compile(r'"sif_ajax_nonce"\s*:\s*"([^"]+)"')

_STORE_DEFS = {
    "SALT LAKE CITY": {
        "source_location_id": "1001",
        "name":     "Tear-A-Part — Salt Lake City, UT",
        "address":  "652 S. Redwood Rd, Salt Lake City, UT 84104",
        "city":     "Salt Lake City",
        "state":    "UT",
        "zip_code": "84104",
        "phone":    "(801) 886-2345",
    },
    "OGDEN": {
        "source_location_id": "1080",
        "name":     "Tear-A-Part — Ogden, UT",
        "address":  "763 W 12th St, Ogden, UT 84404",
        "city":     "Ogden",
        "state":    "UT",
        "zip_code": "84404",
        "phone":    "(801) 564-6960",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # yard_in_date: "2026-05-11T09:12:41.977" (ISO without timezone)
    # yard_date: "05-11-2026" (MM-DD-YYYY) — fallback
    for fmt in (None, "%m-%d-%Y"):
        try:
            if fmt is None:
                return datetime.fromisoformat(raw.strip())
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _fetch_nonce(http: requests.Session, request_auth: RequestAuthClient) -> str:
    """Always fetches fresh — nonce valid ~12 hours, don't cache."""
    logger.info("Fetching nonce from %s", INVENTORY_PAGE_URL)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(
            INVENTORY_PAGE_URL,
            headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"},
            timeout=60,
        )
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    m = _NONCE_RE.search(resp.text)
    if not m:
        raise RuntimeError("sif_ajax_nonce not found in /inventory/ HTML")
    return m.group(1)


def _fetch_store_inventory(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    store_key: str,
    nonce: str,
) -> list[dict]:
    cache_key = f"{AJAX_URL}?action=sif_search_products&store={store_key}"
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        import json
        data = json.loads(entry["content"])
        return data.get("products", [])

    logger.info("POST inventory for store=%s", store_key)
    payload = {
        "action":                "sif_search_products",
        "sif_verify_request":    nonce,
        "sif_form_field_store":  store_key,
        "sif_form_field_make":   "Any",
        "sif_form_field_model":  "Any",
        "sorting[key]":          "iyear",
        "sorting[state]":        "0",
        "sorting[type]":         "int",
    }
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.post(
            AJAX_URL,
            data=payload,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"sif_search_products failed for {store_key}: {data}")

    web_cache.store(cache_key, resp.text, CLIENT_NAME)
    return data.get("products", [])


def _parse_record(record: dict, location_id: int) -> dict | None:
    vin = (record.get("vin") or "").strip()
    if not vin or len(vin) != 17:
        return None

    stock = (record.get("stocknumber") or "").strip() or None
    mileage_raw = record.get("mileage")
    mileage = None
    if mileage_raw:
        try:
            v = int(str(mileage_raw).strip())
            if v > 0:
                mileage = v
        except (ValueError, TypeError):
            pass

    extras: dict = {}
    if stock:
        extras["stock_number"] = stock

    return {
        "vin":          vin,
        "location_id":  location_id,
        "year":         record.get("iyear") and int(str(record["iyear"]).strip()) or None,
        "make":         (record.get("make") or "").strip() or None,
        "model":        (record.get("model") or "").strip() or None,
        "color":        (record.get("color") or "").strip() or None,
        "row":          (record.get("vehicle_row") or "").strip() or None,
        "mileage":      mileage,
        "arrival_date": _parse_arrival_date(record.get("yard_in_date") or record.get("yard_date")),
        "extras":       extras or None,
    }


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for store_key, defn in _STORE_DEFS.items():
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
        location_ids[store_key] = obj.id
    return location_ids


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
                mileage=data.get("mileage"),
                arrival_date=data.get("arrival_date"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "location_id":  data["location_id"],
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "color":        data.get("color"),
                    "row":          data.get("row"),
                    "mileage":      data.get("mileage"),
                    "arrival_date": data.get("arrival_date"),
                    "extras":       data.get("extras"),
                    "last_seen_at": now,
                    "is_active":    True,
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
        http = requests.Session()
        nonce = _fetch_nonce(http, request_auth)
        logger.info("Nonce acquired: %s", nonce)

        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            all_vehicles: list[dict] = []
            skipped = 0
            for store_key, defn in _STORE_DEFS.items():
                location_id = location_ids[store_key]
                records = _fetch_store_inventory(http, web_cache, request_auth, store_key, nonce)
                logger.info("  %s: %d records", store_key, len(records))
                for record in records:
                    parsed = _parse_record(record, location_id)
                    if parsed:
                        all_vehicles.append(parsed)
                    else:
                        skipped += 1

        if skipped:
            logger.info("Skipped %d records (no valid VIN)", skipped)

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(db, all_vehicles, now)

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total=%d",
            new_c, updated_c, removed_c, len(all_vehicles),
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(all_vehicles)
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
