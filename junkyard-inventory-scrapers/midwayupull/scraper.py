#!/usr/bin/env python3
# Site:     Midway U Pull (https://midwayupull.com)
# Platform: URG iis-pro-upull (U-Pull variant of IIS Pro v2)
# Strategy: parse makes from /search-inventory/ HTML → POST admin-ajax.php for models
#           → GET /inventory/{MAKE}/{MODEL}/ → regex parse .car-details-uPull cards
# No /latest-arrivals/ — always full crawl; deactivate removed vehicles on each run.
# Dedup key: VIN (stored as source_key); stock_number stored in extras.
# Source identifier: "midway_upull"

import logging
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

BASE_URL                = "https://midwayupull.com/"
AJAX_URL                = "https://midwayupull.com/wp-admin/admin-ajax.php"
DOMAIN                  = "midwayupull.com"
SOURCE                  = "midway_upull"
CLIENT_NAME             = "midway_upull"
CDN_BASE                = "https://da8h1v3w8q6n5.cloudfront.net/mo06/images"

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

# Location name as it appears in card text → source_location_id
_LOCATION_NAME_TO_YARD: dict[str, str] = {
    "Liberty U-Pull": "MO09",
    "Muncie U-Pull":  "MO38",
}

_LOCATION_DEFS = {
    "MO09": {
        "source_location_id": "MO09",
        "name":     "Midway U Pull — Liberty, MO",
        "address":  "1101 Old State Hwy 210, Liberty, MO 64068",
        "city":     "Liberty",
        "state":    "MO",
        "zip_code": "64068",
        "phone":    "816-781-4886",
    },
    "MO38": {
        "source_location_id": "MO38",
        "name":     "Midway U Pull — Kansas City, KS (Muncie)",
        "address":  "6345 Kansas Ave, Kansas City, KS 66111",
        "city":     "Kansas City",
        "state":    "KS",
        "zip_code": "66111",
        "phone":    "913-287-6185",
    },
    "UNKNOWN": {
        "source_location_id": "UNKNOWN",
        "name":     "Midway U Pull — Location Unknown",
        "address":  None,
        "city":     None,
        "state":    None,
        "zip_code": None,
        "phone":    None,
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_url_slug(text: str) -> str:
    """Convert a display-name string to the iis-pro-upull URL slug format."""
    return text.replace(" ", "_").replace("-", "~").replace("/", ".")


def _fetch(
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


def _post_ajax(
    http: requests.Session,
    request_auth: RequestAuthClient,
    action: str,
    params: dict,
) -> dict:
    """POST to admin-ajax.php; returns parsed JSON. Not cached (small, fast responses)."""
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.post(
            AJAX_URL,
            data={"action": action, **params},
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()
    return resp.json()


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_arrival_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_card(card_div) -> dict | None:
    """
    Parse a single .car-details-uPull div using regex on the full text block.
    Returns None if VIN is missing or invalid.
    """
    text = card_div.get_text("\n")

    vin_m = re.search(r"Vin\s*:\s*([A-HJ-NPR-Z0-9]{17})", text, re.I)
    if not vin_m:
        return None
    vin = vin_m.group(1).strip()

    stock_m = re.search(r"Stock:\s*(\S+)", text)
    stock = stock_m.group(1).strip() if stock_m else None

    year_m = re.search(r"Year:\s*(\d{4})", text)
    year = _parse_year(year_m.group(1)) if year_m else None

    make, model = None, None
    mm_m = re.search(r"Make/Model:\s*(.+)", text)
    if mm_m:
        parts = mm_m.group(1).strip().split(None, 1)
        make = parts[0] if parts else None
        model = parts[1] if len(parts) > 1 else None

    location_m = re.search(r"Location:\s*(.+)", text)
    location_name = location_m.group(1).strip() if location_m else ""
    yard_id = _LOCATION_NAME_TO_YARD.get(location_name, "UNKNOWN")
    if yard_id == "UNKNOWN" and location_name:
        logger.warning("Unrecognised location name %r — assigning UNKNOWN", location_name)

    row_m = re.search(r"Row:\s*(\S+)", text)
    row = row_m.group(1).strip() if row_m else None

    set_date_m = re.search(r"Set Date:\s*([\d/-]+)", text)
    arrival_date = _parse_arrival_date(set_date_m.group(1)) if set_date_m else None

    preview_image_url = f"{CDN_BASE}/{stock}/{stock}_0.jpg" if stock else None

    return {
        "stock":             stock,
        "yard_id":           yard_id,
        "vin":               vin,
        "year":              year,
        "make":              make,
        "model":             model,
        "row":               row,
        "arrival_date":      arrival_date,
        "preview_image_url": preview_image_url,
    }


def _parse_vehicle_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results, skipped = [], 0
    for card in soup.find_all("div", class_="car-details-uPull"):
        parsed = _parse_card(card)
        if parsed:
            results.append(parsed)
        else:
            skipped += 1
    if skipped:
        logger.debug("Skipped %d cards (no VIN)", skipped)
    return results


def _fetch_makes(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[str]:
    """Parse make option values from the /search-inventory/ page."""
    html = _fetch(http, web_cache, request_auth, BASE_URL + "search-inventory/")
    soup = BeautifulSoup(html, "html.parser")

    select = soup.find("select", attrs={"name": re.compile(r"make", re.I)})
    if not select:
        select = soup.find("select", id=re.compile(r"make", re.I))

    makes = []
    if select:
        for opt in select.find_all("option"):
            val = opt.get("value", "").strip()
            if val and val.upper() not in ("", "ALL", "SELECT MAKE"):
                makes.append(val)

    if not makes:
        # Fallback to the known make list from recon (May 2026)
        makes = [
            "ACURA", "ALFA ROMEO", "AMC", "AUDI", "AUSTIN-HEALEY", "BMW",
            "BUICK", "CADILLAC", "CHEVROLET", "CHRYSLER", "DAEWOO", "DAIHATSU",
            "DODGE", "EAGLE", "FIAT", "FORD", "FREIGHTLINER", "GEO", "GMC",
            "HONDA", "HUMMER", "HYUNDAI", "INFINITI", "INTERNATIONAL", "ISUZU",
            "JAGUAR", "JEEP", "KIA", "LAND ROVER", "LEXUS", "LINCOLN", "MAZDA",
            "MERCEDES-BENZ", "MERCURY", "MG", "MINI", "MITSUBISHI", "NISSAN",
            "OLDSMOBILE", "OPEL", "PETERBILT", "PEUGEOT", "PLYMOUTH", "PONTIAC",
            "PORSCHE", "RAM", "RENAULT", "SAAB", "SATURN", "SCION", "SMART",
            "STERLING", "SUBARU", "SUZUKI", "TESLA", "TOYOTA", "TRIUMPH",
            "VOLKSWAGEN", "VOLVO",
        ]
        logger.warning("Could not parse makes from page — using hardcoded fallback (%d makes)", len(makes))

    logger.info("Found %d makes", len(makes))
    return makes


def _fetch_models_ajax(
    http: requests.Session,
    request_auth: RequestAuthClient,
    make: str,
) -> list[str]:
    """Returns model URL slugs for the given make via AJAX POST."""
    data = _post_ajax(http, request_auth, "getAllModelsIISupull", {"make": make})
    return [m["value"] for m in data.get("models", []) if m.get("value")]


def _full_crawl(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[dict]:
    vehicles: dict[str, dict] = {}
    makes = _fetch_makes(http, web_cache, request_auth)
    for make in makes:
        make_slug = _to_url_slug(make)
        models = _fetch_models_ajax(http, request_auth, make)
        if not models:
            continue
        for model_slug in models:
            url = BASE_URL + f"inventory/{make_slug}/{model_slug}/"
            html = _fetch(http, web_cache, request_auth, url)
            for card in _parse_vehicle_cards(html):
                vehicles[card["vin"]] = card
        logger.info("  %s: %d unique vehicles so far", make, len(vehicles))
    logger.info("Full crawl complete: %d unique vehicles", len(vehicles))
    return list(vehicles.values())


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for yard_id, defn in _LOCATION_DEFS.items():
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=yard_id).first()
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
        location_ids[yard_id] = obj.id
    return location_ids


def _get_known_vins(db: Session) -> set[str]:
    rows = (
        db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True))
        .all()
    )
    return {r[0] for r in rows}


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
        location_id = location_ids.get(data["yard_id"], location_ids["UNKNOWN"])
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
                preview_image_url=data.get("preview_image_url"),
                extras={"stock_number": data["stock"]} if data.get("stock") else None,
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
                    "row":               data.get("row"),
                    "arrival_date":      data.get("arrival_date"),
                    "preview_image_url": data.get("preview_image_url"),
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
            vehicles = _full_crawl(http, web_cache, request_auth)

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(
                db, location_ids, vehicles, now
            )

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
