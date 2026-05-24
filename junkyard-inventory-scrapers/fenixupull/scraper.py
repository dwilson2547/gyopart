#!/usr/bin/env python3
# Site:     Fenix U-Pull (https://fenixupull.com)
# Strategy: location × make × model SSR GET → parse <table> rows (50-row server cap)
# Incremental: /recent-inventory/ per location (fnx_location cookie) — skip if all VINs known
# Dedup key: VIN (stored as source_key); stock_number → extras["stock_number"]
# Source identifier: "fenix_upull"

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

BASE_URL                = "https://fenixupull.com"
DOMAIN                  = "fenixupull.com"
SOURCE                  = "fenix_upull"
CLIENT_NAME             = "fenix_upull"
RECENT_URL              = "https://fenixupull.com/recent-inventory/"
MODELS_URL              = "https://fenixupull.com/wp-json/api/getModels"

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

MAKES = [
    "ACURA", "AUDI", "BMW", "BUICK", "CADILLAC", "CHEVROLET", "CHRYSLER", "DODGE",
    "FIAT", "FORD", "FREIGHTLINER", "GMC", "HONDA", "HUMMER", "HYUNDAI", "INFINITI",
    "ISUZU", "JAGUAR", "JEEP", "KIA", "LAND ROVER", "LEXUS", "LINCOLN", "MAZDA",
    "MERCEDES-BENZ", "MERCURY", "MINI", "MITSUBISHI", "NISSAN", "OLDSMOBILE",
    "PONTIAC", "RAM", "SAAB", "SATURN", "SCION", "SUBARU", "SUZUKI", "TOYOTA",
    "TRIUMPH", "VOLKSWAGEN", "VOLVO",
]

_LOCATION_DEFS = {
    "elmira-ny": {
        "source_location_id": "elmira-ny",
        "name":     "Fenix U-Pull — Elmira, NY",
        "address":  "1592 Sears Road, Elmira, NY 14903",
        "city":     "Elmira",
        "state":    "NY",
        "zip_code": "14903",
        "phone":    "(607) 739-3851",
        "fnx_cookie_id": 1,
    },
    "binghamton-ny": {
        "source_location_id": "binghamton-ny",
        "name":     "Fenix U-Pull — Binghamton, NY",
        "address":  "230 Colesville Rd, Binghamton, NY 13904",
        "city":     "Binghamton",
        "state":    "NY",
        "zip_code": "13904",
        "phone":    "(607) 775-1900",
        "fnx_cookie_id": 2,
    },
    "east-syracuse-ny": {
        "source_location_id": "east-syracuse-ny",
        "name":     "Fenix U-Pull — East Syracuse, NY",
        "address":  "7030 Myers Road, East Syracuse, NY 13057",
        "city":     "East Syracuse",
        "state":    "NY",
        "zip_code": "13057",
        "phone":    "(315) 656-7533",
        "fnx_cookie_id": 3,
    },
    "moultrie-ga": {
        "source_location_id": "moultrie-ga",
        "name":     "Fenix U-Pull — Moultrie, GA",
        "address":  "232 Industrial Road, Moultrie, GA 31768",
        "city":     "Moultrie",
        "state":    "GA",
        "zip_code": "31768",
        "phone":    "(229) 985-1052",
        "fnx_cookie_id": 4,
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
        return datetime.strptime(raw.strip(), "%m/%d/%y")
    except ValueError:
        return None


def _fetch(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
    cookies: dict | None = None,
    cache_key_suffix: str = "",
) -> str:
    cache_key = url + cache_key_suffix
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.debug("GET %s", url)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, cookies=cookies, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(cache_key, resp.text, CLIENT_NAME)
    return resp.text


def _fetch_models(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    make: str,
) -> list[str]:
    url = f"{MODELS_URL}?make={make}"
    entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        import json
        return json.loads(entry["content"])

    logger.debug("GET models for %s", make)
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.json()


def _parse_inventory_table(html: str, location_id: int, slug: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []

    vehicles = []
    rows = tbody.find_all("tr")
    if len(rows) == 50:
        logger.warning("Exactly 50 rows for %s — may be hitting server cap", slug)

    for tr in rows:
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue

        def cell(i: int) -> str:
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        # Columns: [0]=Make [1]=Model [2]=Year [3]=Row [4]=VIN [5]=Stock# [6]=Date [7]=Location [8]=Images [9]=More
        vin = cell(4)
        if not vin or len(vin) != 17:
            continue

        stock = cell(5) or None
        vehicles.append({
            "vin":          vin,
            "location_id":  location_id,
            "year":         _parse_year(cell(2)),
            "make":         cell(0) or None,
            "model":        cell(1) or None,
            "row":          cell(3) or None,
            "arrival_date": _parse_arrival_date(cell(6)),
            "extras":       {"stock_number": stock} if stock else None,
        })
    return vehicles


def _extract_vins_from_table(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return set()
    tbody = table.find("tbody")
    if not tbody:
        return set()
    vins = set()
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) > 4:
            vin = cells[4].get_text(strip=True)
            if vin and len(vin) == 17:
                vins.add(vin)
    return vins


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for slug, defn in _LOCATION_DEFS.items():
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
        location_ids[slug] = obj.id
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
                    "location_id":  data["location_id"],
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

            # Fast path: check recent inventory per location
            if known_vins:
                all_recent_known = True
                for slug, defn in _LOCATION_DEFS.items():
                    cookie_id = defn["fnx_cookie_id"]
                    html = _fetch(
                        http, web_cache, request_auth, RECENT_URL,
                        cookies={"fnx_location": str(cookie_id)},
                        cache_key_suffix=f"?fnx_location={cookie_id}",
                    )
                    recent_vins = _extract_vins_from_table(html)
                    if recent_vins and not recent_vins.issubset(known_vins):
                        all_recent_known = False
                        break

                if all_recent_known:
                    logger.info("All recent VINs known across all locations — skipping full crawl")
                    with Session(engine) as db:
                        run = db.get(ScrapeRun, run_id)
                        run.completed_at = _utcnow()
                        run.total_in_feed = len(known_vins)
                        run.new_vehicles = 0
                        run.updated_vehicles = 0
                        run.removed_vehicles = 0
                        run.success = True
                        db.commit()
                    return

            # Build models per make (cached)
            models_by_make: dict[str, list[str]] = {}
            for make in MAKES:
                models = _fetch_models(http, web_cache, request_auth, make)
                models_by_make[make] = [m for m in models if m]

            # Full crawl: location × make × model
            vehicles_by_vin: dict[str, dict] = {}
            total_requests = 0
            for slug, defn in _LOCATION_DEFS.items():
                location_id = location_ids[slug]
                for make in MAKES:
                    for model in models_by_make.get(make, []):
                        url = (
                            f"{BASE_URL}/inventory/"
                            f"?location={slug}&make={make}&model={model}"
                        )
                        html = _fetch(http, web_cache, request_auth, url)
                        total_requests += 1
                        for v in _parse_inventory_table(html, location_id, slug):
                            vehicles_by_vin[v["vin"]] = v

            logger.info(
                "Full crawl: %d requests → %d unique vehicles",
                total_requests, len(vehicles_by_vin),
            )

        vehicles = list(vehicles_by_vin.values())
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
