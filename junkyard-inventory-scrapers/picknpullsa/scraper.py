#!/usr/bin/env python3
# Site:     Pick n Pull San Antonio (https://picknpullsa.com)
# Strategy: single GET /vehicle-inventory/ → parse <table id="vehicles-inventory">
# Columns:  Year, Make, Model, Color, VIN, Engine, Row, Arrival Date
# Note:     Pre-1981 vehicles may have short manufacturer serials (< 17 chars) — stored as-is.
# Dedup key: VIN / serial (stored as source_key); engine → extras["engine"]
# Source identifier: "picknpullsa"

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

INVENTORY_URL           = "https://picknpullsa.com/vehicle-inventory/"
DOMAIN                  = "picknpullsa.com"
SOURCE                  = "picknpullsa"
CLIENT_NAME             = "picknpullsa"

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
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
        return datetime.strptime(raw.strip(), "%m/%d/%y")
    except ValueError:
        return None


def _fetch_page(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> str:
    entry = web_cache.get(INVENTORY_URL, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        logger.info("Cache hit for inventory page")
        return entry["content"]

    logger.info("GET %s", INVENTORY_URL)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(INVENTORY_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(INVENTORY_URL, resp.text, CLIENT_NAME)
    return resp.text


def _parse_inventory(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "vehicles-inventory"})
    if not table:
        raise ValueError("Inventory table 'vehicles-inventory' not found — possible selector drift")
    tbody = table.find("tbody")
    if not tbody:
        raise ValueError("No <tbody> in 'vehicles-inventory' table")

    vehicles, skipped = [], 0
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 8:
            skipped += 1
            continue

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True)

        # Columns: Year, Make, Model, Color, VIN, Engine, Row, Arrival Date
        vin = cell(4)
        if not vin:
            skipped += 1
            continue

        engine = cell(5) or None
        vehicles.append({
            "vin":          vin,
            "year":         _parse_year(cell(0)),
            "make":         cell(1) or None,
            "model":        cell(2) or None,
            "color":        cell(3) or None,
            "row":          cell(6) or None,
            "arrival_date": _parse_arrival_date(cell(7)),
            "extras":       {"engine": engine} if engine else None,
        })

    logger.info("Parsed %d vehicles (%d skipped)", len(vehicles), skipped)
    return vehicles


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Pick n Pull San Antonio",
            address="11795 Applewhite Rd, San Antonio, TX 78224",
            city="San Antonio",
            state="TX",
            zip_code="78224",
            phone="+1 210-298-5420",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def _upsert_vehicles(
    db: Session,
    location_id: int,
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
        # Store short pre-1981 serials in vin column as-is; mapping pipeline handles them.
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=vin,
                vin=vin if len(vin) == 17 else None,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
                row=data.get("row"),
                arrival_date=data.get("arrival_date"),
                extras=data.get("extras"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "year":         data.get("year"),
                    "make":         data.get("make"),
                    "model":        data.get("model"),
                    "color":        data.get("color"),
                    "row":          data.get("row"),
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
        location_id = _ensure_location(db, now)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()
            html = _fetch_page(http, web_cache, request_auth)

        vehicles = _parse_inventory(html)

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(db, location_id, vehicles, now)

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
