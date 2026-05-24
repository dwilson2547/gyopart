#!/usr/bin/env python3
# Site:     Budget U-Pull-It (https://budgetupullit.com)
# Strategy: enumerate 39 makes → GET /current-inventory/?make={MAKE}&model= → last .resultsTable
# Incremental: check /new-arrivals/ first — if all VINs known, skip full crawl.
# Columns:  Year, Make, Model, Stock#, Row, VIN, Date (MM.DD.YY)
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "budget_upullit"

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

BASE_URL                = "https://budgetupullit.com/"
DOMAIN                  = "budgetupullit.com"
SOURCE                  = "budget_upullit"
CLIENT_NAME             = "budget_upullit"
NEW_ARRIVALS_URL        = "https://budgetupullit.com/new-arrivals/"

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

MAKES = [
    "ACURA", "ALFA ROMEO", "AUDI", "BMW", "BUICK", "CADILLAC", "CHEVROLET",
    "CHRYSLER", "DODGE", "FIAT", "FORD", "GEO", "GMC", "HONDA", "HYUNDAI",
    "INFINITI", "JAGUAR", "JEEP", "KIA", "LEXUS", "LINCOLN", "MAZDA",
    "MERCEDES-BENZ", "MERCURY", "MINI", "MITSUBISHI", "NISSAN", "OLDSMOBILE",
    "PONTIAC", "PORSCHE", "RAM", "SATURN", "SCION", "SMART", "SUBARU",
    "SUZUKI", "TOYOTA", "VOLKSWAGEN", "VOLVO",
]


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
    # Current inventory uses MM.DD.YY; new-arrivals uses MM/DD/YY
    for fmt in ("%m.%d.%y", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _fetch(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
    params: dict | None = None,
) -> str:
    cache_key = url + ("?" + "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "")
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.info("GET %s params=%s", url, params)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, params=params, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(cache_key, resp.text, CLIENT_NAME)
    return resp.text


def _parse_results_table(html: str) -> list[dict]:
    """Parse the last .resultsTable on the page (inventory pages have two: header + results)."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="resultsTable")
    if not tables:
        return []
    table = tables[-1]

    vehicles, skipped = [], 0
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 6:
            skipped += 1
            continue

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True)

        # Columns: Year, Make, Model, Stock#, Row, VIN, Date
        vin = cell(5)
        if not vin or len(vin) != 17:
            skipped += 1
            continue

        stock = cell(3) or None
        vehicles.append({
            "vin":          vin,
            "year":         _parse_year(cell(0)),
            "make":         cell(1) or None,
            "model":        cell(2) or None,
            "row":          cell(4) or None,
            "arrival_date": _parse_arrival_date(cell(6)) if len(cells) > 6 else None,
            "extras":       {"stock_number": stock} if stock else None,
        })

    return vehicles


def _parse_new_arrivals_vins(html: str) -> set[str]:
    """Extract VINs from the /new-arrivals/ page (column 4 of the results table)."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="resultsTable")
    if not tables:
        return set()
    table = tables[-1]

    vins = set()
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        # new-arrivals columns: Year, Make, Model, Row, VIN, Arrival Date, Image
        if len(cells) >= 5:
            vin = cells[4].get_text(strip=True)
            if vin and len(vin) == 17:
                vins.add(vin)
    return vins


def _full_crawl(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[dict]:
    vehicles: dict[str, dict] = {}
    for make in MAKES:
        html = _fetch(
            http, web_cache, request_auth,
            BASE_URL + "current-inventory/",
            params={"make": make, "model": ""},
        )
        for v in _parse_results_table(html):
            vehicles[v["vin"]] = v
        logger.info("  %s: %d unique vehicles so far", make, len(vehicles))
    logger.info("Full crawl complete: %d unique vehicles", len(vehicles))
    return list(vehicles.values())


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Budget U-Pull-It",
            address="881 South 9th Street, Winter Garden, FL 34787",
            city="Winter Garden",
            state="FL",
            zip_code="34787",
            phone="407-656-4707",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def _get_known_vins(db: Session) -> set[str]:
    rows = (
        db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True))
        .all()
    )
    return {r[0] for r in rows}


def _upsert_vehicles(
    db: Session,
    location_id: int,
    vehicles: list[dict],
    now: datetime,
    deactivate_removed: bool,
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
                location_id=location_id,
                source=SOURCE,
                source_key=vin,
                vin=vin,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
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

    removed_count = 0
    if deactivate_removed:
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
        known_vins = _get_known_vins(db)
        run = ScrapeRun(source=SOURCE, location_id=location_id, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            skip_full_crawl = False
            if known_vins:
                arrivals_html = _fetch(http, web_cache, request_auth, NEW_ARRIVALS_URL)
                arrivals_vins = _parse_new_arrivals_vins(arrivals_html)
                if arrivals_vins and arrivals_vins.issubset(known_vins):
                    logger.info(
                        "All %d new-arrivals VINs already known — skipping full crawl",
                        len(arrivals_vins),
                    )
                    skip_full_crawl = True

            if skip_full_crawl:
                vehicles = []
                new_c = updated_c = removed_c = 0
            else:
                vehicles = _full_crawl(http, web_cache, request_auth)
                with Session(engine) as db:
                    new_c, updated_c, removed_c = _upsert_vehicles(
                        db, location_id, vehicles, now, deactivate_removed=True
                    )

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total=%d  skipped=%s",
            new_c, updated_c, removed_c, len(vehicles), skip_full_crawl,
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(vehicles) if not skip_full_crawl else None
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
