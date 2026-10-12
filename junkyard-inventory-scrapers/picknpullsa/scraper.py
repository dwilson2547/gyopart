#!/usr/bin/env python3
# Site:     Pick n Pull San Antonio (https://picknpullsa.com)
# Strategy: GET /inventory?page=N (≈24 rows per page) → parse <table class="inv-table">  (site redesigned 2026;
#           was a single /vehicle-inventory/ table)
# Columns:  Year, Make, Model, Color, Stock #, VIN, Engine, Row, Arrival, Inquire
# Note:     Pre-1981 vehicles may have short manufacturer serials (< 17 chars) — stored as-is.
# Dedup key: VIN / serial (stored as source_key); engine → extras["engine"]
# Source identifier: "picknpullsa"

import logging
import re
import sys
from pathlib import Path
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

# scrape_contract.py lives one level up in the repo and next to scraper.py in the image.
sys.path.append(str(Path(__file__).resolve().parent.parent))
from scrape_contract import Broken, run  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INVENTORY_URL           = "https://picknpullsa.com/inventory"
MAX_PAGES               = 400  # ≈ 9,600 vehicles; the yard advertises 3,500+
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
    page: int,
) -> str:
    url = f"{INVENTORY_URL}?page={page}"
    entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.info("GET %s", url)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise Broken(f"429 rate limited by {SOURCE}")
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.text


def _parse_inventory(html: str) -> tuple[list[dict], bool]:
    """Vehicles on one page, and whether the page links to a next one."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="inv-table")
    if not table:
        raise Broken("Inventory table 'inv-table' not found — possible layout change")

    vehicles, skipped = [], 0
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue  # header row (th) or a short row

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True)

        # Columns: Year, Make, Model, Color, Stock #, VIN, Engine, Row, Arrival, Inquire
        vin = cell(5)
        if not vin:
            skipped += 1
            continue

        extras = {k: v for k, v in (("engine", cell(6)), ("stock_number", cell(4))) if v}
        vehicles.append({
            "vin":          vin,
            "year":         _parse_year(cell(0)),
            "make":         cell(1) or None,
            "model":        cell(2) or None,
            "color":        cell(3) or None,
            "row":          cell(7) or None,
            "arrival_date": _parse_arrival_date(cell(8)),
            "extras":       extras or None,
        })
    if skipped:
        logger.debug("Skipped %d rows without a VIN", skipped)
    has_next = soup.find("a", href=re.compile(r"[?&]page=\d+")) is not None and bool(vehicles)
    return vehicles, has_next


def _fetch_inventory(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[dict]:
    """Walk the pages until one comes back empty. Rows can shift between pages while we crawl, so
    vehicles are de-duplicated by VIN."""
    by_vin: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        vehicles, has_next = _parse_inventory(_fetch_page(http, web_cache, request_auth, page))
        new = [v for v in vehicles if v["vin"] not in by_vin]
        for v in vehicles:
            by_vin[v["vin"]] = v
        # Past the end the site may repeat the last page instead of returning an empty one.
        if not vehicles or not has_next or not new:
            break
    else:
        logger.warning("Stopped at MAX_PAGES=%d — inventory may be incomplete", MAX_PAGES)
    logger.info("Parsed %d vehicles over %d pages", len(by_vin), page)
    return list(by_vin.values())


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


def main() -> dict:
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
            vehicles = _fetch_inventory(http, web_cache, request_auth)

        if not vehicles:
            raise Broken("0 vehicles parsed — possible layout change")

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

        return {"items": len(vehicles), "new": new_c, "updated": updated_c, "removed": removed_c}

    except Broken as exc:
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
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
    run(main)
