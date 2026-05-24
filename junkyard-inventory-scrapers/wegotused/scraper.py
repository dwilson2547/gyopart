#!/usr/bin/env python3
# Site:     WeGotUsed / Harry's U-Pull It (https://wegotused.com)
# Platform: WordPress + inventory-7lt plugin (AngularJS frontend, SSR data)
# Strategy: paginated GET newest-first → stop on first known VIN (incremental)
#           First run (no known VINs): paginate all pages, then deactivate missing
# Dedup key: VIN (stored as source_key)
# Source identifier: "wegotused"

import logging
import math
import os
import re
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

INVENTORY_URL           = "https://wegotused.com/our-inventory/"
DOMAIN                  = "wegotused.com"
SOURCE                  = "wegotused"
CLIENT_NAME             = "wegotused"

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
}

_TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+records", re.IGNORECASE)

_LOCATION_DEFS = {
    "ALLENTOWN": {
        "source_location_id": "allentown",
        "name":     "Harry's U-Pull It — Allentown, PA",
        "address":  "1510 East Jonathan Street, Allentown, PA",
        "city":     "Allentown",
        "state":    "PA",
        "phone":    "(610) 433-9901",
    },
    "PENNSBURG": {
        "source_location_id": "pennsburg",
        "name":     "Harry's U-Pull It — Pennsburg, PA",
        "address":  "2557 Geryville Pike, Pennsburg, PA 18073",
        "city":     "Pennsburg",
        "state":    "PA",
        "zip_code": "18073",
        "phone":    "(215) 541-9950",
    },
    "HAZLE TOWNSHIP": {
        "source_location_id": "hazle-township",
        "name":     "Harry's U-Pull It — Hazle Township, PA",
        "address":  "1010 Winters Avenue, Hazle Township, PA 18202",
        "city":     "Hazle Township",
        "state":    "PA",
        "zip_code": "18202",
        "phone":    "(570) 459-9901",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_arrival_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def _fetch_page(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    page: int,
) -> str:
    url = (
        f"{INVENTORY_URL}"
        f"?inv%5Byard%5D=all&inv%5Bmake%5D=&inv%5Bmodel%5D=&inv%5Bmanufacturer%5D="
        f"&inv%5Byear%5D=&inv%5Bpart%5D=&inv%5Bpage%5D={page}&inv%5Bsort%5D%5Byard_date%5D=0"
    )
    entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.debug("GET page %d", page)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.text


def _parse_results(html: str) -> tuple[list[dict], int]:
    """Returns (rows, total_record_count). total_record_count=0 if not found."""
    soup = BeautifulSoup(html, "html.parser")
    results_div = soup.select_one("#_results")
    if not results_div:
        return [], 0

    total = 0
    m = _TOTAL_RE.search(results_div.get_text())
    if m:
        total = int(m.group(1).replace(",", ""))

    rows = []
    for tr in results_div.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        # Columns: [0]=Yard [1]=Year [2]=Make [3]=Model [4]=Manufacturer [5]=Color [6]=YardDate [7]=Row [8]=VIN
        vin = cell(8)
        if not vin or len(vin) != 17:
            continue

        yard_city = cell(0)
        rows.append({
            "vin":          vin,
            "yard_city":    yard_city,
            "year":         int(cell(1)) if cell(1).isdigit() else None,
            "make":         cell(2) or None,
            "model":        cell(3) or None,
            "color":        cell(5) or None,
            "row":          cell(7) or None,
            "arrival_date": _parse_arrival_date(cell(6)),
        })
    return rows, total


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for yard_city, defn in _LOCATION_DEFS.items():
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
                address=defn.get("address"),
                city=defn["city"],
                state=defn["state"],
                zip_code=defn.get("zip_code"),
                phone=defn.get("phone"),
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        location_ids[yard_city] = obj.id
    return location_ids


def _upsert_vehicles(
    db: Session,
    location_ids: dict[str, int],
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
        location_id = location_ids.get(data["yard_city"])
        if location_id is None:
            logger.debug("Unknown yard city %r — skipping VIN %s", data["yard_city"], vin)
            continue

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
                row=data.get("row"),
                arrival_date=data.get("arrival_date"),
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
                    "color":        data.get("color"),
                    "row":          data.get("row"),
                    "arrival_date": data.get("arrival_date"),
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
        location_ids = _ensure_locations(db, now)
        run = ScrapeRun(source=SOURCE, location_id=None, started_at=now)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    with Session(engine) as db:
        known_vins: set[str] = {
            row[0]
            for row in db.query(Vehicle.source_key)
            .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True))
            .all()
        }

    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            # Page 0 gives us total count and first batch
            html0 = _fetch_page(http, web_cache, request_auth, 0)
            first_rows, total = _parse_results(html0)
            if total == 0:
                logger.warning("No records found or could not parse total — aborting")
                raise RuntimeError("Empty inventory response")

            total_pages = math.ceil(total / 15)
            logger.info("Total records: %d (%d pages)", total, total_pages)

            all_vehicles: list[dict] = []
            stopped_early = False

            for page in range(total_pages):
                if page == 0:
                    rows = first_rows
                else:
                    html = _fetch_page(http, web_cache, request_auth, page)
                    rows, _ = _parse_results(html)

                for row in rows:
                    if known_vins and row["vin"] in known_vins:
                        logger.info(
                            "Known VIN %s on page %d — stopping early", row["vin"], page
                        )
                        stopped_early = True
                        break
                    all_vehicles.append(row)

                if stopped_early:
                    break

            logger.info(
                "Crawl done — %d new vehicles collected (stopped_early=%s)",
                len(all_vehicles), stopped_early,
            )

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(
                db, location_ids, all_vehicles, now,
                deactivate_removed=not stopped_early,
            )

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total_collected=%d",
            new_c, updated_c, removed_c, len(all_vehicles),
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = total if not stopped_early else None
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
