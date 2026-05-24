#!/usr/bin/env python3
# Site:     Ryan's Pick-a-Part — Detroit, MI
# Strategy: Playwright response interception (autorecycler.io elasticsearch/msearch)
# Dedup key: api_id (_id from ES) stored as source_key
# Source identifier: "ryans_pic_a_part"
# Extras JSONB: inventory_id, name, exterior_color, added_date_ms, api_modified_ms
# Output DB: shared junkyard_inventory Postgres (JUNKYARD_DATABASE_URL)

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Response
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from junkyard_common.models import Location, ScrapeRun, Vehicle
from junkyard_common.db import get_engine
from cache_client import WebCacheClient
from request_auth_client import RequestAuthClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INVENTORY_URL           = "https://app.autorecycler.io/inventory/ryans-pick-a-part-detroit"
SOURCE                  = "ryans_pic_a_part"
CLIENT_NAME             = "ryans_pic_a_part"
WEBCACHE_URL            = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
WEBCACHE_TIMEOUT        = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
REQUEST_AUTH_SERVER_URL = os.environ.get("REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000")

SCROLL_WAIT_S           = 2.5
MAX_IDLE_SCROLLS        = 6
SCROLL_INTERVAL_S       = 1.5
INVENTORY_CACHE_KEY     = f"{INVENTORY_URL}#full_inventory_scrape"
INVENTORY_CACHE_MAX_AGE = 6 * 3600


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_vehicle_source(src: dict) -> dict | None:
    name = src.get("name_text")
    if not name:
        return None

    parts = name.split(" ", 2)
    year  = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
    make  = parts[1] if len(parts) > 1 else None
    model = parts[2] if len(parts) > 2 else None

    preview = src.get("preview_image_image")
    if preview and preview.startswith("//"):
        preview = "https:" + preview

    canonical = {
        "year":              year,
        "make":              make,
        "model":             model,
        "vin":               src.get("vin_text"),
        "row":               src.get("row_text"),
        "preview_image_url": preview,
    }
    extras = {
        "inventory_id":    src.get("inventory_id_text"),
        "name":            name,
        "exterior_color":  src.get("exterior_color_text"),
        "added_date_ms":   src.get("added_date_date"),
        "api_modified_ms": src.get("Modified Date"),
    }
    canonical["extras"] = {k: v for k, v in extras.items() if v is not None} or None
    return canonical


def _ensure_location(db: Session, now: datetime) -> int:
    obj = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
    if obj is None:
        obj = Location(
            source=SOURCE,
            source_location_id="1",
            name="Ryan's Pick-a-Part — Detroit",
            city="Detroit",
            state="MI",
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj.id


def upsert_vehicles(
    db: Session,
    location_id: int,
    pairs: list[tuple[str, dict]],
    now: datetime,
) -> tuple[int, int, int]:
    current_api_ids = {api_id for api_id, _ in pairs}

    existing_ids: set[str] = {
        row[0]
        for row in db.query(Vehicle.source_key)
        .filter(Vehicle.source == SOURCE, Vehicle.source_key.in_(current_api_ids))
        .all()
    }

    new_count = updated_count = 0

    for api_id, data in pairs:
        stmt = (
            pg_insert(Vehicle)
            .values(
                location_id=location_id,
                source=SOURCE,
                source_key=api_id,
                year=data.get("year"),
                make=data.get("make"),
                model=data.get("model"),
                vin=data.get("vin"),
                row=data.get("row"),
                preview_image_url=data.get("preview_image_url"),
                extras=data.get("extras"),
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
                    "vin":               data.get("vin"),
                    "row":               data.get("row"),
                    "preview_image_url": data.get("preview_image_url"),
                    "extras":            data.get("extras"),
                    "last_seen_at":      now,
                    "is_active":         True,
                },
            )
        )
        db.execute(stmt)
        if api_id in existing_ids:
            updated_count += 1
        else:
            new_count += 1

    removed_count = (
        db.query(Vehicle)
        .filter(Vehicle.source == SOURCE, Vehicle.is_active.is_(True),
                ~Vehicle.source_key.in_(current_api_ids))
        .update({"is_active": False}, synchronize_session="fetch")
    )

    db.commit()
    return new_count, updated_count, removed_count


async def scrape_inventory(web_cache, request_auth) -> list[tuple[str, dict]]:
    cached = web_cache.get(INVENTORY_CACHE_KEY, max_age=INVENTORY_CACHE_MAX_AGE)
    if cached:
        logger.info("Cache hit for full inventory — skipping browser run")
        data = json.loads(cached["content"])
        return [(item["api_id"], item["data"]) for item in data]

    collected: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = await context.new_page()

        async def handle_response(response: Response) -> None:
            if "elasticsearch/msearch" not in response.url:
                return
            try:
                body = await response.body()
                data = json.loads(body)
            except Exception:
                return
            for resp in data.get("responses", []):
                for hit in resp.get("hits", {}).get("hits", []):
                    if hit.get("_type") != "custom.inventorysearch":
                        continue
                    api_id = hit.get("_id")
                    if not api_id:
                        continue
                    parsed = _parse_vehicle_source(hit.get("_source", {}))
                    if parsed is not None:
                        collected[api_id] = parsed

        page.on("response", handle_response)

        domain = "app.autorecycler.io"
        with request_auth.acquire(domain) as permit:
            logger.info("Navigating to inventory page: %s", INVENTORY_URL)
            response = await page.goto(INVENTORY_URL, wait_until="networkidle", timeout=60_000)
            permit.set_status(response.status if response else 200)
        await asyncio.sleep(SCROLL_WAIT_S)

        idle_scroll_count = prev_count = 0
        while idle_scroll_count < MAX_IDLE_SCROLLS:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_WAIT_S + SCROLL_INTERVAL_S)
            current_count = len(collected)
            if current_count == prev_count:
                idle_scroll_count += 1
            else:
                idle_scroll_count = 0
                logger.info("Collected %d vehicles (+%d)", current_count, current_count - prev_count)
            prev_count = current_count

        logger.info("Scroll loop complete. Total collected: %d", len(collected))
        await browser.close()

    result = list(collected.items())
    web_cache.store(
        INVENTORY_CACHE_KEY,
        json.dumps([{"api_id": api_id, "data": data} for api_id, data in result]),
        CLIENT_NAME,
    )
    return result


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
            pairs = asyncio.run(scrape_inventory(web_cache, request_auth))

        if not pairs:
            raise RuntimeError("No vehicles collected — possible site change or block.")

        with Session(engine) as db:
            new_c, updated_c, removed_c = upsert_vehicles(db, location_id, pairs, now)

        logger.info("Run complete — new=%d  updated=%d  removed=%d  total_in_feed=%d",
                    new_c, updated_c, removed_c, len(pairs))

        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.total_in_feed = len(pairs)
            run.new_vehicles = new_c
            run.updated_vehicles = updated_c
            run.removed_vehicles = removed_c
            run.success = True
            db.commit()

    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        with Session(engine) as db:
            run = db.get(ScrapeRun, run_id)
            run.completed_at = _utcnow()
            run.error_message = str(exc)[:1000]
            run.success = False
            db.commit()
        sys.exit(1)

    finally:
        request_auth.close()


if __name__ == "__main__":
    main()
