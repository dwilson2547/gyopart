#!/usr/bin/env python3
# Site:     Chesterfield Auto Parts (https://chesterfieldauto.com)
# Platform: ASP.NET Core MVC; anti-forgery token + make-enumeration POST
# Strategy: GET /newest-cars for delta check → GET token + makes → POST per make → parse table + modals
# Dedup key: VIN (stored as source_key); extras["stock_number"], extras["transmission"], extras["drive"]
# Source identifier: "chesterfield_auto"

import logging
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup, NavigableString
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL                = "https://chesterfieldauto.com"
SEARCH_URL              = f"{BASE_URL}/search-our-inventory-by-location"
NEWEST_URL              = f"{BASE_URL}/newest-cars"
DOMAIN                  = "chesterfieldauto.com"
SOURCE                  = "chesterfield_auto"
CLIENT_NAME             = "chesterfield_auto"

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

_VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}$")

_LOCATION_DEFS = {
    "Richmond": {
        "source_location_id": "richmond",
        "name":     "Chesterfield Auto Parts — Richmond, VA",
        "address":  "5111 Old Midlothian Tpke, Richmond, VA 23224",
        "city":     "Richmond",
        "state":    "VA",
        "zip_code": "23224",
        "phone":    "(804) 233-5481",
    },
    "Fort Lee": {
        "source_location_id": "fort-lee",
        "name":     "Chesterfield Auto Parts — Fort Lee, VA",
        "address":  "4855 Puddledock Rd, Prince George, VA 23875",
        "city":     "Prince George",
        "state":    "VA",
        "zip_code": "23875",
        "phone":    "(804) 732-9253",
    },
    "Southside": {
        "source_location_id": "southside",
        "name":     "Chesterfield Auto Parts — Southside, VA",
        "address":  "12910 Genito Rd, Midlothian, VA 23112",
        "city":     "Midlothian",
        "state":    "VA",
        "zip_code": "23112",
        "phone":    "(804) 744-0716",
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
        return datetime.strptime(raw.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def _fetch_get(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    url: str,
    use_cache: bool = True,
) -> str:
    if use_cache:
        entry = web_cache.get(url, max_age=CACHE_MAX_AGE_SECONDS)
        if entry:
            return entry["content"]

    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(url, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    if use_cache:
        web_cache.store(url, resp.text, CLIENT_NAME)
    return resp.text


def _fetch_post(
    http: requests.Session,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    make_id: str,
    token: str,
) -> str:
    cache_key = f"{SEARCH_URL}?SelectedMake.Id={make_id}"
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    logger.debug("POST make_id=%s", make_id)
    payload = {
        "SelectedMake":            make_id,
        "BasicSearch.ModelId":     "0",
        "BasicSearch.BeginYear":   "",
        "BasicSearch.EndYear":     "",
        "__RequestVerificationToken": token,
    }
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.post(
            f"{SEARCH_URL}?SelectedMake.Id={make_id}",
            data=payload,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        permit.set_status(resp.status_code)
        if resp.status_code == 429:
            logger.error("429 received — aborting run")
            raise SystemExit(1)
        resp.raise_for_status()

    web_cache.store(cache_key, resp.text, CLIENT_NAME)
    return resp.text


def _parse_modal_extras(soup: BeautifulSoup, make_upper: str, vin: str) -> dict:
    """Extract stock number, transmission, drive from the pre-rendered Bootstrap modal."""
    extras: dict = {}
    modal = soup.find("div", id=f"{make_upper}{vin}")
    if not modal:
        return extras
    for b_tag in modal.find_all("b"):
        key = b_tag.get_text(strip=True).rstrip(":")
        sibling = b_tag.next_sibling
        val = str(sibling).strip() if isinstance(sibling, NavigableString) else ""
        if not val:
            continue
        if "Stock Number" in key:
            extras["stock_number"] = val
        elif "Transmission" in key:
            extras["transmission"] = val
        elif "Drive" in key:
            extras["drive"] = val
    return extras


def _parse_results(html: str, location_ids: dict[str, int]) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []

    vehicles = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 10:
            continue

        # [0]=Pics(button) [1]=Store [2]=Make [3]=Model [4]=Year
        # [5]=Color [6]=Body [7]=Engine [8]=YardRow [9]=Set(date)
        btn = cells[0].find("button", attrs={"data-target": True})
        if not btn:
            continue
        target = btn["data-target"].lstrip("#")
        m = _VIN_RE.search(target)
        if not m:
            continue
        vin = m.group()

        store_text = cells[1].get_text(strip=True)
        location_id = location_ids.get(store_text)
        if location_id is None:
            logger.debug("Unknown store %r — skipping VIN %s", store_text, vin)
            continue

        make_upper = cells[2].get_text(strip=True).upper()
        extras = _parse_modal_extras(soup, make_upper, vin)

        engine = cells[7].get_text(strip=True)
        if engine:
            extras["engine"] = engine

        vehicles.append({
            "vin":          vin,
            "location_id":  location_id,
            "year":         _parse_year(cells[4].get_text(strip=True)),
            "make":         cells[2].get_text(strip=True) or None,
            "model":        cells[3].get_text(strip=True) or None,
            "color":        cells[5].get_text(strip=True) or None,
            "row":          cells[8].get_text(strip=True) or None,
            "arrival_date": _parse_arrival_date(cells[9].get_text(strip=True)),
            "extras":       extras or None,
        })
    return vehicles


def _extract_vins(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    vins = set()
    for btn in soup.find_all("button", attrs={"data-target": True}):
        target = btn["data-target"].lstrip("#")
        m = _VIN_RE.search(target)
        if m:
            vins.add(m.group())
    return vins


def _get_token_and_makes(http: requests.Session, request_auth: RequestAuthClient) -> tuple[str, list[dict]]:
    """Always fetches fresh — token is session-scoped, do not cache."""
    with request_auth.acquire(DOMAIN) as permit:
        resp = http.get(SEARCH_URL, headers=HEADERS, timeout=60)
        permit.set_status(resp.status_code)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_input:
        raise RuntimeError("__RequestVerificationToken not found")
    token = token_input["value"]
    makes = [
        {"id": opt["value"], "name": opt.get_text(strip=True)}
        for opt in soup.select("select#selected-make option")
        if opt.get("value") and opt["value"] not in ("", "0")
    ]
    logger.info("Token acquired; %d makes found", len(makes))
    return token, makes


def _ensure_locations(db: Session, now: datetime) -> dict[str, int]:
    location_ids = {}
    for store_name, defn in _LOCATION_DEFS.items():
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
        location_ids[store_name] = obj.id
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
        http = requests.Session()
        http.headers.update(HEADERS)

        with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
            # Delta check: if all newest-cars VINs are known, skip full crawl
            newest_html = _fetch_get(http, web_cache, request_auth, NEWEST_URL, use_cache=True)
            newest_vins = _extract_vins(newest_html)
            if known_vins and newest_vins and newest_vins.issubset(known_vins):
                logger.info("All %d newest-cars VINs known — skipping full crawl", len(newest_vins))
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

            # Full crawl: extract token + makes, POST per make
            token, makes = _get_token_and_makes(http, request_auth)

            vehicles_by_vin: dict[str, dict] = {}
            for make in makes:
                html = _fetch_post(http, web_cache, request_auth, make["id"], token)
                for v in _parse_results(html, location_ids):
                    vehicles_by_vin[v["vin"]] = v
            logger.info("Full crawl: %d makes → %d unique vehicles", len(makes), len(vehicles_by_vin))

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
