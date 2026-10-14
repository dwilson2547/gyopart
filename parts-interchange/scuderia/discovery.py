"""Discovery: queue every OE model variant Scuderia lists (docs/design.md §3).

Walks the part-finder: marque → model → the model's `Original Parts` (OE) product type → its variants.
Tuning-only models have no OE product type and are skipped, so the OE marques come out of the site, not
a list here. Each variant is upserted into `scrape_target` (the parts-direct work queue, reused as is):
make = marque slug, model = model slug, trim = variant id, year = '' (the column is NOT NULL; years come
from the variant name at write time), engine NULL.

A marque with OE variants but no `manufacturer` row (matched on lower(name) = the marque's display name)
is skipped and reported: adding a marque is deliberate, and the user inserts its row.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

from catalog import BASE_URL, Option, parse_marques, parse_models, parse_oe_link, parse_variants

# parts-direct's queue functions, reused unchanged (same table, same claim/lease semantics).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parts-direct" / "update-scraper"))
import work_queue as q  # noqa: E402

CONFIG = "scuderia"
# /part-finder/ itself redirects home; any marque page carries the full marque list.
START_URL = BASE_URL + "/part-finder/ferrari"
# Land Rover: parts-direct's jaguar site already covers it (user, 2026-10-14).
SKIP_MARQUES = {"landrover"}


@dataclass(frozen=True)
class Variant:
    marque: Option
    model: Option
    variant: Option

    @property
    def variant_id(self) -> str:
        return self.variant.slug


Listing = Callable[..., Awaitable]


async def oe_variants(listing: Listing, skip: set[str] = SKIP_MARQUES,
                      out_of_time: Callable[[], bool] = lambda: False) -> AsyncIterator[Variant]:
    """Every OE variant, marque by marque. `listing(url, parse)` fetches and parses one page."""
    for marque in await listing(START_URL, parse_marques):
        if marque.slug in skip:
            continue
        for model in await listing(marque.url, parse_models):
            if out_of_time():
                return
            # A tuning-only model redirects to its /aftermarket/ catalogue: no OE.
            oe = await listing(model.url, parse_oe_link, on_redirect=None)
            if oe is None:
                continue
            for variant in await listing(oe, parse_variants):
                yield Variant(marque, model, variant)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_name() -> str:
    return f"{CONFIG}:discovery"


def due(cur, interval_days: int) -> bool:
    cur.execute("SELECT max(completed_at) FROM scrape_run WHERE manufacturer = %s AND success", (run_name(),))
    last = cur.fetchone()[0]
    return last is None or (utcnow() - last).days >= interval_days


class Queue:
    """Upserts discovered variants; one manufacturer lookup per marque."""

    def __init__(self, conn):
        self.conn = conn
        self._mfr: dict[str, int | None] = {}
        self.found = self.new = 0
        self.missing_manufacturer: dict[str, int] = {}

    def manufacturer_id(self, cur, marque: Option) -> int | None:
        if marque.slug not in self._mfr:
            cur.execute("SELECT id FROM manufacturer WHERE lower(name) = lower(%s)", (marque.name,))
            row = cur.fetchone()
            self._mfr[marque.slug] = row[0] if row else None
        return self._mfr[marque.slug]

    def add(self, v: Variant) -> None:
        with self.conn.cursor() as cur:
            mfr = self.manufacturer_id(cur, v.marque)
            if mfr is None:
                self.missing_manufacturer[v.marque.name] = self.missing_manufacturer.get(v.marque.name, 0) + 1
                return
            self.new += q.upsert_discovered(cur, mfr, "", v.marque.slug, v.model.slug, v.variant_id, None,
                                            v.variant.url)
            self.found += 1
        self.conn.commit()

    def record(self, started: datetime) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scrape_run (manufacturer, started_at, completed_at, cars_processed, new_parts,
                                           updated_parts, success, error_message)
                   VALUES (%s, %s, %s, %s, 0, 0, true, %s)""",
                (run_name(), started, utcnow(), self.found,
                 f"discovery: {self.found} variants listed, {self.new} new; no manufacturer row: "
                 f"{self.missing_manufacturer or 'none'}"[:1000]),
            )
        self.conn.commit()


async def dry_run(args) -> dict:
    """List every OE variant without a database: sizes the catalogue (design §7 step 1)."""
    import grpc
    from cache_client import WebCacheClient
    from request_auth_client import RequestAuthClient

    from scraper import BrowserTransport, Collector

    with grpc.insecure_channel(args.request_auth) as channel:
        await asyncio.to_thread(grpc.channel_ready_future(channel).result, timeout=10)
    auth = RequestAuthClient(args.request_auth)
    transport = BrowserTransport(auth, cdp_url=args.cdp_url, timeout_ms=args.timeout * 1000)
    per_marque: dict[str, dict] = {}
    try:
        with WebCacheClient(args.webcache) as web_cache:
            collector = Collector(web_cache, None, transport, bucket=args.bucket, max_age=args.max_age)
            await collector.load_robots()
            async for v in oe_variants(collector.listing):
                m = per_marque.setdefault(v.marque.name, {"models": set(), "variants": 0})
                m["models"].add(v.model.slug)
                m["variants"] += 1
                print(json.dumps({"marque": v.marque.name, "model": v.model.name, "variant": v.variant.name,
                                  "url": v.variant.url}), flush=True)
            stats = dict(collector.stats)
    finally:
        try:
            await transport.close()
        finally:
            auth.close()
    return {"marques": {k: {"models": len(m["models"]), "variants": m["variants"]} for k, m in per_marque.items()},
            "variants": sum(m["variants"] for m in per_marque.values()), **stats}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="List Scuderia's OE variants (--dry-run: no database).")
    ap.add_argument("--dry-run", action="store_true", required=True)
    ap.add_argument("--bucket", default=os.environ.get("CACHE_BUCKET", "scuderia"))
    ap.add_argument("--max-age", type=int, default=23 * 3600)
    ap.add_argument("--webcache", default=os.environ.get("WEBCACHE_URL"))
    ap.add_argument("--request-auth", default=os.environ.get("REQUEST_AUTH_SERVER_URL"))
    ap.add_argument("--cdp-url", default=os.environ.get("BROWSERLESS_URL"))
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args(argv)
    if not (args.cdp_url and args.webcache and args.request_auth):
        ap.error("set BROWSERLESS_URL, WEBCACHE_URL and REQUEST_AUTH_SERVER_URL")
    print(json.dumps(asyncio.run(dry_run(args)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
