#!/usr/bin/env python3
# Site:     Pull-N-Save (https://pullnsave.com)
# Platform: WordPress + legacy gm_vehicle_search plugin (PnsV1_3.3)
# Strategy: POST admin-ajax.php action=getVehicles per store × make → parse HTML table
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "pull_n_save"

import logging
import os
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AJAX_URL                = "https://pullnsave.com/wp-admin/admin-ajax.php"
DOMAIN                  = "pullnsave.com"
SOURCE                  = "pull_n_save"
CLIENT_NAME             = "pull_n_save"

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Content-Type": "application/x-www-form-urlencoded",
}

_STORE_DEFS = {
    1: {"source_location_id": "1", "name": "Pull-N-Save — Salt Lake City, UT",  "city": "Salt Lake City", "state": "UT", "store_name": "Salt Lake City"},
    2: {"source_location_id": "2", "name": "Pull-N-Save — Phoenix South, AZ",   "city": "Phoenix",        "state": "AZ", "store_name": "Phoenix - South"},
    3: {"source_location_id": "3", "name": "Pull-N-Save — Glendale, AZ",        "city": "Glendale",       "state": "AZ", "store_name": "Glendale"},
    4: {"source_location_id": "4", "name": "Pull-N-Save — Phoenix North, AZ",   "city": "Phoenix",        "state": "AZ", "store_name": "Phoenix - North"},
    5: {"source_location_id": "5", "name": "Pull-N-Save — Gilbert, UT",         "city": "Gilbert",        "state": "UT", "store_name": "Gilbert"},
    6: {"source_location_id": "6", "name": "Pull-N-Save — Springville, UT",     "city": "Springville",    "state": "UT", "store_name": "Springville"},
    7: {"source_location_id": "7", "name": "Pull-N-Save — Tucson, AZ",          "city": "Tucson",         "state": "AZ", "store_name": "Tucson"},
    9: {"source_location_id": "9", "name": "Pull-N-Save — Riverside, CA",       "city": "Riverside",      "state": "CA", "store_name": "Riverside"},
}

# Map store name string from HTML response → store number for location lookup
_STORE_NAME_TO_ID: dict[str, int] = {v["store_name"]: k for k, v in _STORE_DEFS.items()}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_year(raw: str) -> int | None:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return None


def _parse_arrival_date(raw: str) -> datetime | None:
    if not raw:
        return None
    # data-value is ISO date "2026-05-15"; visible text may differ
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _post_ajax(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    store_id: int,
    make: str,
) -> str:
    cache_key = f"{AJAX_URL}?action=getVehicles&store={store_id}&make={make}"
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.debug("POST getVehicles store=%d make=%s", store_id, make)
    payload = {
        "action": "getVehicles",
        "store":  str(store_id),
        "makes":  make,
        "models": "0",
    }
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.post(AJAX_URL, data=payload, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(cache_key, resp.text, CLIENT_NAME)
    return resp.text


def _get_makes(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[str]:
    cache_key = f"{AJAX_URL}?action=getMakes"
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        html = entry["content"]
    else:
        logger.info("POST getMakes")
        with request_auth.acquire(DOMAIN) as permit:
            resp = http.post(
                AJAX_URL,
                data={"action": "getMakes"},
                headers=HEADERS,
                timeout=30,
            )
            permit.set_status(resp.status_code)
            resp.raise_for_status()
        web_cache.store(cache_key, resp.text, CLIENT_NAME)
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    return [
        opt["value"]
        for opt in soup.find_all("option")
        if opt.get("value") and opt["value"] not in ("", "0")
    ]


def _parse_vehicle_table(html: str, make: str, location_ids: dict[int, int]) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="vehicletable1")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []

    vehicles = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue

        # Columns: [0]=img [1]=Year [2]=Model [3]=Date Received [4]=Row
        #           [5]=Store [6]=Color [7]=Stock# [8]=VIN
        vin = cells[8].get_text(strip=True)
        if not vin or len(vin) != 17:
            continue

        store_name = cells[5].get_text(strip=True)
        store_id = _STORE_NAME_TO_ID.get(store_name)
        if store_id is None:
            logger.debug("Unknown store name %r — skipping VIN %s", store_name, vin)
            continue
        location_id = location_ids.get(store_id)
        if location_id is None:
            continue

        date_td = cells[3]
        date_raw = date_td.get("data-value") or date_td.get_text(strip=True)

        stock = cells[7].get_text(strip=True) or None
        stock_full = f"{stock}-{store_id}" if stock else None

        vehicles.append({
            "vin":               vin,
            "location_id":       location_id,
            "year":              _parse_year(cells[1].get_text(strip=True)),
            "make":              make,
            "model":             cells[2].get_text(strip=True) or None,
            "color":             cells[6].get_text(strip=True) or None,
            "row":               cells[4].get_text(strip=True) or None,
            "arrival_date":      _parse_arrival_date(date_raw),
            "preview_image_url": (
                f"https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/{stock_full}/OrderId/1"
                if stock_full else None
            ),
            "extras":            {"stock_number": stock} if stock else None,
        })
    return vehicles


def _ensure_locations(db: Session, now: datetime) -> dict[int, int]:
    location_ids = {}
    for store_id, defn in _STORE_DEFS.items():
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
                city=defn["city"],
                state=defn["state"],
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        location_ids[store_id] = obj.id
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
        location_ids = _ensure_locations(db, now)
        run = ScrapeRun(source=SOURCE, location_id=None, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            makes = _get_makes(http, web_cache, request_auth)
            logger.info("Makes: %d", len(makes))

            vehicles_by_vin: dict[str, dict] = {}
            skipped = 0
            for store_id in _STORE_DEFS:
                for make in makes:
                    html = _post_ajax(http, web_cache, request_auth, store_id, make)
                    for v in _parse_vehicle_table(html, make, location_ids):
                        vehicles_by_vin[v["vin"]] = v
                logger.info("  store=%d done — %d unique vehicles so far", store_id, len(vehicles_by_vin))

        vehicles = list(vehicles_by_vin.values())
        logger.info("Total unique vehicles: %d", len(vehicles))

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
