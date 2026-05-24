#!/usr/bin/env python3
# Site:     iPull-uPull Auto Parts (https://ipullupull.com)
# Strategy: download 4 CSV files (one per yard) → csv.DictReader → upsert
# Feeds:    https://ipullupull.com/{fresno|pomona|sacramento|stockton}.csv
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "ipullupull"

import csv
import io
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

BASE_CSV_URL            = "https://ipullupull.com/{yard}.csv"
DOMAIN                  = "ipullupull.com"
SOURCE                  = "ipullupull"
CLIENT_NAME             = "ipullupull"

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

_YARD_DEFS = {
    "fresno": {
        "source_location_id": "fresno",
        "name":     "iPull-uPull — Fresno, CA",
        "address":  "2274 East Muscat Avenue, Fresno, CA 93725",
        "city":     "Fresno",
        "state":    "CA",
        "zip_code": "93725",
        "phone":    "+1 (559) 445-4117",
    },
    "pomona": {
        "source_location_id": "pomona",
        "name":     "iPull-uPull — Pomona, CA",
        "address":  "1560 East Mission Boulevard, Pomona, CA 91766",
        "city":     "Pomona",
        "state":    "CA",
        "zip_code": "91766",
        "phone":    "+1 (909) 623-6108",
    },
    "sacramento": {
        "source_location_id": "sacramento",
        "name":     "iPull-uPull — Sacramento, CA",
        "address":  "7600 Stockton Boulevard, Sacramento, CA 95823",
        "city":     "Sacramento",
        "state":    "CA",
        "zip_code": "95823",
        "phone":    "+1 (916) 409-3080",
    },
    "stockton": {
        "source_location_id": "stockton",
        "name":     "iPull-uPull — Stockton, CA",
        "address":  "3151 S. Hwy 99 Frontage Road, Stockton, CA 95215",
        "city":     "Stockton",
        "state":    "CA",
        "zip_code": "95215",
        "phone":    "+1 (209) 425-0489",
    },
}


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
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d")
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


def _fetch_yard_csv(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    yard: str,
) -> list[dict]:
    url = BASE_CSV_URL.format(yard=yard)
    content = _fetch_text(http, web_cache, request_auth, url)
    reader = csv.DictReader(io.StringIO(content))
    # Strip leading spaces from all header keys (CSV has e.g. " VIN", " Stock#")
    return [{k.strip(): v for k, v in row.items()} for row in reader]


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for yard, defn in _YARD_DEFS.items():
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=yard).first()
        if obj is None:
            obj = Location(
                source=SOURCE,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
                **defn,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        location_ids[yard] = obj.id
    return location_ids


def _upsert_vehicles(
    db: Session,
    location_ids: dict[str, int],
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
        location_id = location_ids[data["yard"]]

        extras: dict = {}
        if stock := data.get("stock_number"):
            extras["stock_number"] = stock
        if data.get("fresh_set"):
            extras["fresh_set"] = True

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
                row=data.get("row"),
                arrival_date=data.get("arrival_date"),
                extras=extras or None,
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "location_id":  location_id,
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "row":          data.get("row"),
                    "arrival_date": data.get("arrival_date"),
                    "extras":       extras or None,
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
        vehicles: list[dict] = []
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            for yard in _YARD_DEFS:
                rows = _fetch_yard_csv(http, web_cache, request_auth, yard)
                yard_vehicles = []
                skipped = 0
                for row in rows:
                    vin = row.get("VIN", "").strip()
                    if not vin or len(vin) != 17:
                        skipped += 1
                        continue
                    yard_vehicles.append({
                        "yard":         yard,
                        "vin":          vin,
                        "year":         _parse_year(row.get("Year")),
                        "make":         row.get("Make", "").strip() or None,
                        "model":        row.get("Model", "").strip() or None,
                        "row":          row.get("Row", "").strip() or None,
                        "arrival_date": _parse_arrival_date(row.get("Date Added")),
                        "stock_number": row.get("Stock#", "").strip() or None,
                        "fresh_set":    row.get("Fresh Set", "").strip() == "Yes",
                    })
                logger.info("  %s: %d vehicles (%d skipped)", yard, len(yard_vehicles), skipped)
                vehicles.extend(yard_vehicles)

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(db, location_ids, vehicles, now)

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
