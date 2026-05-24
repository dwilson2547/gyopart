#!/usr/bin/env python3
# Site:     Stricker Auto Parts (https://strickerautoparts.com)
# Platform: URG IIS Pro v2 — SSR make/model crawl
# Strategy: GET /parts/makes/ → /parts/{MAKE}/ → /parts/{MAKE}/{MODEL}/ → parse .card-price divs
# Card data: 2-column <table> rows (key/value), NOT <b>Label:</b> text
# Dedup key: VIN (stored as source_key)
# Source identifier: "stricker_auto_parts"

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

BASE_URL                = "https://strickerautoparts.com/"
DOMAIN                  = "strickerautoparts.com"
SOURCE                  = "stricker_auto_parts"
CLIENT_NAME             = "stricker_auto_parts"

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


def _table_data(card_div) -> dict[str, str]:
    """Extract key/value pairs from 2-column <tr><td>Key:</td><td>Value</td></tr> table rows."""
    data = {}
    for row in card_div.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).rstrip(":")
            val = cells[1].get_text(strip=True)
            if key and val:
                data[key] = val
    return data


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_mileage(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip().replace(",", ""))
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


def _slug_to_label(slug: str) -> str:
    """Convert URL slug to display form: ALFA_ROMEO → ALFA ROMEO."""
    return slug.replace("_", " ")


def _parse_card(
    card_div,
    make_hint: str | None = None,
    model_hint: str | None = None,
) -> dict | None:
    """
    Parse a single .card.card-price vehicle card.
    make_hint / model_hint are URL slugs used as fallbacks when the table omits Make/Model
    (which happens on /parts/{MAKE}/{MODEL}/ pages but not on /latest-arrivals/).
    Returns None if VIN is missing or invalid.
    """
    stock = card_div.get("id", "").strip()
    if not stock:
        return None

    data = _table_data(card_div)

    vin = data.get("Vin") or data.get("VIN") or data.get("vin")
    if not vin or len(vin.strip()) != 17:
        return None
    vin = vin.strip()

    make = data.get("Make") or (
        _slug_to_label(make_hint) if make_hint else None
    )
    model = data.get("Model") or (
        _slug_to_label(model_hint) if model_hint else None
    )

    img = card_div.find("img")
    preview_image_url = None
    if img:
        src = img.get("data-src") or img.get("src") or ""
        if "cloudfront" in src:
            preview_image_url = src

    return {
        "stock":             stock,
        "vin":               vin,
        "year":              _parse_year(data.get("Year")),
        "make":              make,
        "model":             model,
        "mileage":           _parse_mileage(data.get("Miles")),
        "arrival_date":      _parse_arrival_date(data.get("Enter Date")),
        "preview_image_url": preview_image_url,
    }


def _parse_vehicle_cards(
    html: str,
    make_hint: str | None = None,
    model_hint: str | None = None,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results, skipped = [], 0
    for outer in soup.find_all("div", class_="iis-col-sm-4"):
        card = outer.find("div", class_="card-price")
        if not card:
            continue
        parsed = _parse_card(card, make_hint=make_hint, model_hint=model_hint)
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
    html = _fetch(http, web_cache, request_auth, BASE_URL + "parts/makes/")
    soup = BeautifulSoup(html, "html.parser")
    makes, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/parts/([^/]+)/$", a["href"])
        if m:
            make = m.group(1)
            if make not in seen:
                makes.append(make)
                seen.add(make)
    logger.info("Found %d makes", len(makes))
    return makes


def _fetch_models(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    make: str,
) -> list[str]:
    html = _fetch(http, web_cache, request_auth, BASE_URL + f"parts/{make}/")
    soup = BeautifulSoup(html, "html.parser")
    models, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(rf"/parts/{re.escape(make)}/([^/]+)/$", a["href"])
        if m:
            model = m.group(1)
            if model not in seen:
                models.append(model)
                seen.add(model)
    return models


def _full_crawl(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
) -> list[dict]:
    vehicles: dict[str, dict] = {}
    makes = _fetch_makes(http, web_cache, request_auth)
    for make in makes:
        models = _fetch_models(http, web_cache, request_auth, make)
        for model in models:
            url = BASE_URL + f"parts/{make}/{model}/"
            html = _fetch(http, web_cache, request_auth, url)
            for card in _parse_vehicle_cards(html, make_hint=make, model_hint=model):
                vehicles[card["vin"]] = card
        logger.info("  %s: %d unique vehicles so far", make, len(vehicles))
    logger.info("Full crawl complete: %d unique vehicles", len(vehicles))
    return list(vehicles.values())


def _latest_arrivals_crawl(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    known_vins: set[str],
) -> tuple[list[dict], bool]:
    """
    Returns (new_vehicles, need_full_crawl).
    need_full_crawl=True when no known VIN appears in the 60 latest entries.
    """
    html = _fetch(http, web_cache, request_auth, BASE_URL + "latest-arrivals/")
    cards = _parse_vehicle_cards(html)
    logger.info("Latest arrivals: %d cards", len(cards))

    new_vehicles = []
    for card in cards:
        if card["vin"] in known_vins:
            logger.info("Known VIN %s found — incremental run stops here", card["vin"])
            return new_vehicles, False
        new_vehicles.append(card)

    logger.info("No known VINs in latest-arrivals — falling back to full crawl")
    return [], True


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Stricker Auto Parts",
            address="4955 Benton Road, Batavia, OH 45103",
            city="Batavia",
            state="OH",
            zip_code="45103",
            phone="513-732-1152",
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
    full_crawl_mode: bool,
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
                mileage=data.get("mileage"),
                arrival_date=data.get("arrival_date"),
                preview_image_url=data.get("preview_image_url"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_vehicle_source",
                set_={
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "mileage":           data.get("mileage"),
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

    removed_count = 0
    if full_crawl_mode:
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

    full_crawl_mode = True
    try:
        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            http = requests.Session()

            if not known_vins:
                logger.info("First run — doing full crawl")
                vehicles = _full_crawl(http, web_cache, request_auth)
            else:
                new_vehicles, need_full = _latest_arrivals_crawl(
                    http, web_cache, request_auth, known_vins
                )
                if need_full:
                    vehicles = _full_crawl(http, web_cache, request_auth)
                else:
                    vehicles = new_vehicles
                    full_crawl_mode = False
                    logger.info("Incremental mode: %d new vehicles", len(vehicles))

        with Session(engine) as db:
            new_c, updated_c, removed_c = _upsert_vehicles(
                db, location_id, vehicles, now, full_crawl_mode
            )

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total=%d  mode=%s",
            new_c, updated_c, removed_c, len(vehicles),
            "full_crawl" if full_crawl_mode else "incremental",
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
