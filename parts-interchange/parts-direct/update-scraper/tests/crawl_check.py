"""End-to-end crawl + write for one already-loaded vehicle, served from the 2024 scrape's local page
cache instead of the live site (no browser, no VPN), compared with the bulk-loaded rows, ROLLED BACK.

  PARTS_INTERCHANGE_DATABASE_URL=... python tests/crawl_check.py --data-dir .../fiat --target-car 45637 [--refetch-parts]
"""
import argparse
import bz2
import json
import os
import sys

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("WEBCACHE_URL", "http://unused")
os.environ.setdefault("IMGCACHE_URL", "http://unused")
os.environ.setdefault("REQUEST_AUTH_URL", "unused:9000")
from equivalence_check import COUNTS, snapshot  # noqa: E402
from scraper_v2 import UpdaterV2  # noqa: E402
from writer import Target, write_vehicle  # noqa: E402
from utils.Exceptions import PageRetrievalError  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--target-car", type=int, required=True)
    ap.add_argument("--refetch-parts", action="store_true", help="parse every part page, not just unknown ones")
    a = ap.parse_args()
    cache = json.load(open(os.path.join(a.data_dir, "webcache.json")))
    served = {"n": 0}

    def get_page(url):
        f = cache.get(url)
        if not f:
            raise PageRetrievalError(f"not in local cache: {url}")
        served["n"] += 1
        up.last_final_url = url  # what the live get_page records; cached pages never redirect
        return bz2.decompress(open(os.path.join(a.data_dir, "webcache", f), "rb").read()).decode("utf-8", "ignore")

    up = UpdaterV2("fiat", os.environ["PARTS_INTERCHANGE_DATABASE_URL"])
    up.get_page = get_page
    up.save_image = lambda url, name: True
    from scraper_v2 import ImageQueue
    up.images = ImageQueue(up.save_image, 2)
    if a.refetch_parts:
        up._known_parts = lambda mfr, nums: {}

    conn = psycopg2.connect(os.environ["PARTS_INTERCHANGE_DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT id, manufacturer_id, year, make, model, trim, engine, page_url FROM scrape_target WHERE car_id = %s",
                (a.target_car,))
    t = Target(*cur.fetchone())
    before = snapshot(cur, a.target_car)
    try:
        v = up.crawl(t)
        up.images.close(cancel=False)  # wait for the (stubbed) downloads
        for name, meta in v.images.items():
            meta["saved"] = up.images.status(name)
        print(f"crawl: {served['n']} pages, {len(v.diagrams)} category pages, {len(v.part_numbers)} part numbers, "
              f"{len(v.parts)} part pages parsed, {len(v.images)} images")
        st = write_vehicle(conn, "fiat", t, v)
        after = snapshot(cur, st.car_id)
        ok = st.car_id == a.target_car
        for k in COUNTS:
            same = before[k] == after[k]
            ok &= same
            print(f"  {k:24} loader={before[k]!s:34} crawl+write={after[k]!s:34} {'OK' if same else 'DIFF'}")
        print("EQUIVALENT" if ok else "NOT EQUIVALENT")
    finally:
        conn.rollback()
        print("rolled back")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
