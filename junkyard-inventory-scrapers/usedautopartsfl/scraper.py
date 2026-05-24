#!/usr/bin/env python3
# Site:     ABC Used Auto Parts FL (https://usedautopartsfl.com)
# Data:     Public Google Spreadsheet (via AppSheet) — no auth required
# Strategy: GET CARS4PARTS sheet as CSV → filter active rows → parse → upsert
# Dedup key: VIN where present (source_key=VIN); fallback source_key="STOCK:{stock#}"
# Source identifier: "used_auto_parts_fl"

import csv
import io
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from dateutil import parser as dateutil_parser
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SPREADSHEET_ID          = "1HySo6ksil-jl6McltcYui6TBC7UvOCMqd754uw4EpOc"
APPSHEET_APP_ID         = "bcd4e61e-096c-4961-9dee-534e93c3e3ab"
APPSHEET_USER_ID        = "1250151"
SHEET_NAME              = "CARS4PARTS"
DOMAIN                  = "docs.google.com"
SOURCE                  = "used_auto_parts_fl"
CLIENT_NAME             = "used_auto_parts_fl"

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

_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    f"/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

# Known multi-word makes for YMM parsing
_MULTIWORD_MAKES = {
    "MERCEDES BENZ", "LAND ROVER", "ALFA ROMEO", "ASTON MARTIN",
    "ROLLS ROYCE", "CHEVROLET GMC",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_ymm(ymm: str) -> tuple[int | None, str | None, str | None]:
    """Parse 'YEAR MAKE MODEL' string → (year, make, model)."""
    parts = ymm.strip().split()
    if not parts:
        return None, None, None

    year = None
    if parts[0].isdigit() and len(parts[0]) == 4:
        year = int(parts[0])
        remainder = " ".join(parts[1:])
    else:
        remainder = " ".join(parts)

    if not remainder:
        return year, None, None

    # Check multi-word makes first
    remainder_upper = remainder.upper()
    for mw_make in sorted(_MULTIWORD_MAKES, key=len, reverse=True):
        if remainder_upper.startswith(mw_make):
            make = mw_make.title()
            model = remainder[len(mw_make):].strip() or None
            return year, make, model

    # Single-word make
    rem_parts = remainder.split(None, 1)
    make = rem_parts[0].title() if rem_parts else None
    model = rem_parts[1] if len(rem_parts) > 1 else None
    return year, make, model


def _parse_arrival_date(raw: str) -> datetime | None:
    if not raw or not raw.strip():
        return None
    try:
        return dateutil_parser.parse(raw.strip(), dayfirst=False)
    except Exception:
        return None


def _build_image_url(image_path: str) -> str | None:
    if not image_path or not image_path.strip():
        return None
    encoded = quote(image_path.strip(), safe="")
    return (
        f"https://www.appsheet.com/fsimage.png"
        f"?appid={APPSHEET_APP_ID}"
        f"&datasource=google"
        f"&filename={encoded}"
        f"&tableprovider=google"
        f"&userid={APPSHEET_USER_ID}"
    )


def _fetch_csv(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> str:
    entry = web_cache.get(_SHEET_URL, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.info("GET %s", _SHEET_URL)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(_SHEET_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(_SHEET_URL, resp.text, CLIENT_NAME)
    return resp.text


def _parse_rows(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    active, skipped_sold, skipped_no_key = [], 0, 0

    for row in reader:
        status = (row.get("SOLDMISSINGDAMGED?") or "").upper()
        if "SOLD" in status or "MISSING" in status:
            skipped_sold += 1
            continue

        vin_raw = (row.get("VIN #") or "").strip()
        stock_raw = (row.get("STOCK#") or "").strip()

        vin = vin_raw if len(vin_raw) == 17 else None
        if not vin and not stock_raw:
            skipped_no_key += 1
            continue

        source_key = vin if vin else f"STOCK:{stock_raw}"
        ymm_raw = (row.get("YEAR MAKE & MODEL") or "").strip()
        year, make, model = _parse_ymm(ymm_raw)

        image_path = (row.get("IMAGES") or "").strip()
        preview_image_url = _build_image_url(image_path)

        extras: dict = {}
        if stock_raw:
            extras["stock_number"] = stock_raw

        location_col = (row.get("LOCATION") or "").strip()
        if location_col:
            extras["yard_section"] = location_col

        active.append({
            "source_key":        source_key,
            "vin":               vin,
            "year":              year,
            "make":              make,
            "model":             model,
            "color":             (row.get("Color / Body / Codes") or "").strip() or None,
            "arrival_date":      _parse_arrival_date(row.get("ARRIVAL DATE")),
            "preview_image_url": preview_image_url,
            "extras":            extras or None,
        })

    logger.info(
        "CSV parsed: %d active, %d sold/missing skipped, %d no-key skipped",
        len(active), skipped_sold, skipped_no_key,
    )
    return active


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="ABC Used Auto Parts FL — Orlando, FL",
            address="18609 East Colonial Drive, Orlando, FL 32820",
            city="Orlando",
            state="FL",
            zip_code="32820",
            phone="(407) 287-5100",
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
    current_keys = {v["source_key"] for v in vehicles}

    existing_keys: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_keys))
        .all()
    }

    new_count = updated_count = 0
    for data in vehicles:
        sk = data["source_key"]
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=sk,
                vin=data.get("vin"),
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                color=data.get("color"),
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
                    "vin":               data.get("vin"),
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "color":             data.get("color"),
                    "arrival_date":      data.get("arrival_date"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
                    "last_seen_at":      now,
                    "is_active":         True,
                },
            )
        )
        db.execute(stmt)
        if sk in existing_keys:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(
            Vehicle.source == SOURCE,
            Vehicle.is_active.is_(True),
            ~Vehicle.source_key.in_(current_keys),
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
            csv_text = _fetch_csv(http, web_cache, request_auth)

        vehicles = _parse_rows(csv_text)

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
