#!/usr/bin/env python3
# Site:     Pick Your Part / pyp.com (LKQ network — 62 locations)
# Platform: DotNetNuke CMS; Cloudflare protection requires Playwright browser
# Strategy: browser navigates to pyp.com → extracts location list → page.evaluate() fetches per location
# Incremental: per location, stop pagination when a known VIN is encountered (newest-first order)
# Dedup key: VIN (stored as source_key); extras["stock_id"] = "{locationCode}-{stockNo}"
# Source identifier: "pyp"

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INVENTORY_API_URL       = "https://www.pyp.com/DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx"
SEED_URL                = "https://www.pyp.com/inventory/cincinnati-1253/"
DOMAIN                  = "pyp.com"
SOURCE                  = "pyp"
CLIENT_NAME             = "pyp"

WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")
CACHE_MAX_AGE_SECONDS   = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(23 * 3600)))

_LOCATION_LIST_RE = re.compile(r"var _locationList\s*=\s*(\[.*?\]);", re.DOTALL)
_YMM_RE = re.compile(r"^(\d{4})\s+(.+)$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_available_date(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_inventory_html(html: str, location_id: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    vehicles = []
    for row in soup.select("div.pypvi_resultRow"):
        stock_id = row.get("id", "") or None

        ymm_link = row.select_one("a.pypvi_ymm")
        ymm_text = ymm_link.get_text(separator=" ", strip=True) if ymm_link else ""

        year = make = model = None
        m = _YMM_RE.match(ymm_text)
        if m:
            year_raw, mm = m.group(1), m.group(2)
            year = int(year_raw)
            parts = mm.split(None, 1)
            make = parts[0] if parts else None
            model = parts[1] if len(parts) > 1 else None

        details: dict[str, str] = {}
        for item in row.select("div.pypvi_detailItem"):
            b = item.find("b")
            if b:
                key = b.get_text(strip=True).rstrip(":")
                val = item.get_text(strip=True)
                # remove the label text to get just the value
                val = val[len(b.get_text(strip=True)):].strip()
                if val:
                    details[key] = val

        vin = (details.get("VIN") or "").strip()
        if not vin or len(vin) != 17:
            continue

        time_el = row.select_one("time[datetime]")
        available_iso = time_el["datetime"] if time_el else None

        img_el = row.select_one("a.pypvi_image")
        preview_image_url = img_el["href"] if img_el and img_el.get("href") else None

        row_val = (details.get("Row") or "").strip() or None
        section = (details.get("Section") or "").strip() or None

        extras: dict = {}
        if stock_id:
            extras["stock_id"] = stock_id
        if section:
            extras["section"] = section

        vehicles.append({
            "vin":               vin,
            "location_id":       location_id,
            "year":              year,
            "make":              make,
            "model":             model,
            "color":             (details.get("Color") or "").strip() or None,
            "row":               row_val,
            "arrival_date":      _parse_available_date(available_iso),
            "preview_image_url": preview_image_url,
            "extras":            extras or None,
        })
    return vehicles


async def _fetch_page_html(
    page: Page,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    location_code: str,
    page_num: int,
) -> str:
    cache_key = f"{INVENTORY_API_URL}?page={page_num}&store={location_code}"
    entry = web_cache.get(cache_key, max_age=CACHE_MAX_AGE_SECONDS)
    if entry:
        return entry["content"]

    url = f"{INVENTORY_API_URL}?page={page_num}&filter=&store={location_code}"
    with request_auth.acquire(DOMAIN) as permit:
        html = await page.evaluate(
            """async (url) => {
                const r = await fetch(url, {headers: {'x-requested-with': 'XMLHttpRequest'}});
                if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
                return r.text();
            }""",
            url,
        )
        permit.set_status(200)

    web_cache.store(cache_key, html, CLIENT_NAME)
    return html


async def _scrape_location(
    page: Page,
    web_cache: WebCacheClient,
    request_auth: RequestAuthClient,
    location_code: str,
    location_id: int,
    known_vins: set[str],
) -> tuple[list[dict], bool]:
    """Returns (vehicles, is_full_scrape). is_full_scrape=False if stopped early on known VIN."""
    vehicles_by_vin: dict[str, dict] = {}
    page_num = 1
    stopped_early = False

    while True:
        html = await _fetch_page_html(page, web_cache, request_auth, location_code, page_num)
        parsed = _parse_inventory_html(html, location_id)

        for v in parsed:
            if known_vins and v["vin"] in known_vins:
                stopped_early = True
                break
            vehicles_by_vin[v["vin"]] = v

        if stopped_early or "pypvi_end" in html:
            break
        page_num += 1

    return list(vehicles_by_vin.values()), not stopped_early


def _ensure_locations(db: Session, location_list: list[dict], now: datetime) -> dict[str, int]:
    location_ids: dict[str, int] = {}
    for loc in location_list:
        code = str(loc.get("LocationCode", ""))
        if not code:
            continue
        obj = db.query(Location).filter_by(source=SOURCE, source_location_id=code).first()
        name = f"Pick Your Part — {loc.get('DisplayName', code)}, {loc.get('StateAbbr', '')}"
        if obj is None:
            obj = Location(
                source=SOURCE,
                source_location_id=code,
                name=name,
                address=loc.get("Address"),
                city=loc.get("City"),
                state=loc.get("StateAbbr"),
                zip_code=loc.get("Zip"),
                phone=loc.get("Phone"),
                is_active=True,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        location_ids[code] = obj.id
    return location_ids


def _upsert_and_deactivate(
    db: Session,
    location_id: int,
    vehicles: list[dict],
    now: datetime,
    deactivate_removed: bool,
    existing_vins: set[str],
) -> tuple[int, int, int]:
    current_vins = {v["vin"] for v in vehicles}

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
                color=data.get("color"),
                row=data.get("row"),
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
                    "location_id":       location_id,
                    "year":              data.get("year"),
                    "make":              data.get("make"),
                    "model":             data.get("model"),
                    "color":             data.get("color"),
                    "row":               data.get("row"),
                    "arrival_date":      data.get("arrival_date"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
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
    if deactivate_removed:
        removed_count = (
            db.query(Vehicle)
            .filter(
                Vehicle.source == SOURCE,
                Vehicle.location_id == location_id,
                Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_vins),
            )
            .update({"is_active": False}, synchronize_session="fetch")
        )

    db.commit()
    return new_count, updated_count, removed_count


async def _run() -> None:
    request_auth = RequestAuthClient(REQUEST_AUTH_SERVER_URL)
    engine = get_engine()
    now = _utcnow()

    with Session(engine) as db:
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
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            with WebCacheClient(WEBCACHE_URL, timeout=WEBCACHE_TIMEOUT) as web_cache:
                # Navigate to seed page to clear Cloudflare challenge + extract location list
                logger.info("Navigating to %s", SEED_URL)
                await page.goto(SEED_URL, wait_until="domcontentloaded", timeout=60_000)
                seed_html = await page.content()

                m = _LOCATION_LIST_RE.search(seed_html)
                if not m:
                    raise RuntimeError("_locationList not found in page source")
                location_list = json.loads(m.group(1))
                logger.info("Found %d locations", len(location_list))

                with Session(engine) as db:
                    location_ids = _ensure_locations(db, location_list, now)

                with Session(engine) as db:
                    existing_vins_all: set[str] = {
                        row[0]
                        for row in db.query(Vehicle.source_key)
                        .filter(Vehicle.source == SOURCE)
                        .all()
                    }

                total_new = total_updated = total_removed = total_vehicles = 0

                for loc in location_list:
                    code = str(loc.get("LocationCode", ""))
                    if not code or code not in location_ids:
                        continue
                    location_id = location_ids[code]

                    vehicles, is_full = await _scrape_location(
                        page, web_cache, request_auth, code, location_id, known_vins
                    )
                    logger.info(
                        "  %s (%s): %d vehicles (full=%s)",
                        loc.get("DisplayName", code), code, len(vehicles), is_full,
                    )

                    if vehicles or is_full:
                        with Session(engine) as db:
                            n, u, r = _upsert_and_deactivate(
                                db, location_id, vehicles, now,
                                deactivate_removed=is_full,
                                existing_vins=existing_vins_all,
                            )
                        total_new += n
                        total_updated += u
                        total_removed += r
                        total_vehicles += len(vehicles)

            await browser.close()

        logger.info(
            "Run complete — new=%d  updated=%d  removed=%d  total_collected=%d",
            total_new, total_updated, total_removed, total_vehicles,
        )

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = total_vehicles
            run.new_vehicles = total_new
            run.updated_vehicles = total_updated
            run.removed_vehicles = total_removed
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


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
