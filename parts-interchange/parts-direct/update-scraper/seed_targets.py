"""Seed scrape_target, the update scraper's work queue (design-v2 §3.2). Safe to re-run.

  python seed_targets.py cars                       # one `done` target per existing car
  python seed_targets.py tree --config fiat \
      --data-dir /home/daniel/nfs-share/parts-direct-data/fiat   # classify a scraped tree.json

`cars` mode: every car → status done, last_scraped_at NULL (unknown, so the oldest refresh), keyed by
the select values parts-loader-v2 stored (year.name, make/model/trim/engine.select_value).

`tree` mode, for a scrape whose tree marks vehicles done that never were (the Mopar maintenance-page
incident): each vehicle is classified by its cached landing page —
  has parts in the tree                → done (linked to its car)
  cached real page, no categories      → no_catalog (re-checked on the refresh cycle)
  cached maintenance page / not cached → pending
Existing targets are left alone (ON CONFLICT DO NOTHING), except that `tree` mode upgrades a target
from done to pending when its cached page is the maintenance page.

Connection: PARTS_INTERCHANGE_DATABASE_URL.
"""
from __future__ import annotations

import argparse
import bz2
import json
import os
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

MAINTENANCE_MARKER = "Service Under Maintenance"
CATALOGUE_MARKER = "Select Parts Category"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_from_cars(cur) -> int:
    cur.execute(
        """
        INSERT INTO scrape_target (manufacturer_id, year, make, model, trim, engine, page_url,
                                   status, car_id, attempts, created_at)
        SELECT c.manufacturer_id, y.name, mk.select_value, md.select_value, t.select_value,
               e.select_value, c.base_url, 'done', c.id, 0, %s
        FROM car c
        JOIN year y ON y.id = c.year_id
        JOIN make mk ON mk.id = c.make_id
        JOIN model md ON md.id = c.model_id
        LEFT JOIN trim t ON t.id = c.trim_id
        LEFT JOIN engine e ON e.id = c.engine_id
        ON CONFLICT ON CONSTRAINT uq_scrape_target_vehicle DO NOTHING
        """,
        (now(),),
    )
    return cur.rowcount


def classify(data_dir: str, webcache: dict, page_url: str | None) -> tuple[str, datetime | None]:
    """(status, cached_at) for a vehicle with no parts, from its cached landing page."""
    fname = webcache.get(page_url) if page_url else None
    if not fname:
        return "pending", None
    path = os.path.join(data_dir, "webcache", fname)
    cached_at = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).replace(tzinfo=None)
    html = bz2.decompress(open(path, "rb").read()).decode("utf-8", "ignore")
    if MAINTENANCE_MARKER in html:
        return "pending", None
    if CATALOGUE_MARKER in html:
        return "no_catalog", cached_at
    return "pending", None


def seed_from_tree(cur, config: str, data_dir: str) -> dict:
    cur.execute("SELECT id FROM manufacturer WHERE lower(name) = %s", (config.lower(),))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"manufacturer {config!r} not found")
    mfr_id = row[0]
    tree = json.load(open(os.path.join(data_dir, "tree.json")))
    webcache = json.load(open(os.path.join(data_dir, "webcache.json")))

    rows, counts = [], {"done": 0, "no_catalog": 0, "pending": 0}
    for year, ynode in tree.items():
        for make, mknode in ynode.get("makes", {}).items():
            for model, mdnode in mknode.get("models", {}).items():
                for trim, tnode in mdnode.get("trims", {}).items():
                    for engine, enode in tnode.get("engines", {}).items():
                        url = enode.get("page_url")
                        if enode.get("parts"):
                            status, cached_at = "done", None
                        else:
                            status, cached_at = classify(data_dir, webcache, url)
                        counts[status] += 1
                        rows.append((mfr_id, year, make, model, trim, engine, url, status,
                                     cached_at, 0, now()))

    execute_values(
        cur,
        """
        INSERT INTO scrape_target (manufacturer_id, year, make, model, trim, engine, page_url,
                                   status, last_scraped_at, attempts, created_at)
        VALUES %s
        ON CONFLICT ON CONSTRAINT uq_scrape_target_vehicle DO UPDATE
          SET status = 'pending', last_scraped_at = NULL
          WHERE EXCLUDED.status = 'pending' AND scrape_target.status = 'done'
        """,
        rows,
        page_size=1000,
    )
    # Link done targets to their cars (the cars mode may have created them first, or not at all).
    cur.execute(
        """
        UPDATE scrape_target st SET car_id = c.id
        FROM car c
        JOIN year y ON y.id = c.year_id
        JOIN make mk ON mk.id = c.make_id
        JOIN model md ON md.id = c.model_id
        LEFT JOIN trim t ON t.id = c.trim_id
        LEFT JOIN engine e ON e.id = c.engine_id
        WHERE st.manufacturer_id = %s AND c.manufacturer_id = %s AND st.car_id IS NULL
          AND st.year = y.name AND st.make = mk.select_value AND st.model = md.select_value
          AND st.trim IS NOT DISTINCT FROM t.select_value
          AND st.engine IS NOT DISTINCT FROM e.select_value
        """,
        (mfr_id, mfr_id),
    )
    counts["linked_to_cars"] = cur.rowcount
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("cars")
    t = sub.add_parser("tree")
    t.add_argument("--config", required=True, help="manufacturer config name, e.g. fiat")
    t.add_argument("--data-dir", required=True, help="dir with tree.json, webcache.json, webcache/")
    args = p.parse_args()

    conn = psycopg2.connect(os.environ["PARTS_INTERCHANGE_DATABASE_URL"])
    with conn, conn.cursor() as cur:
        if args.mode == "cars":
            print(f"cars: {seed_from_cars(cur)} targets inserted")
        else:
            print(f"tree {args.config}: {seed_from_tree(cur, args.config, args.data_dir)}")
        cur.execute("SELECT status, count(*) FROM scrape_target GROUP BY status ORDER BY status")
        print("scrape_target now:", dict(cur.fetchall()))


if __name__ == "__main__":
    main()
