"""Writer vs. bulk loader: re-write an already-loaded car from the raw scrape JSON through writer.py
inside a transaction, compare its rows with what parts-loader-v2 produced, then ROLL BACK.

  PARTS_INTERCHANGE_DATABASE_URL=... python tests/equivalence_check.py \
      --data-dir /home/daniel/nfs-share/parts-direct-data/fiat --config fiat --target-car 45637

Leaves the database unchanged whatever happens.
"""
import argparse
import json
import os
import sys

import ijson
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from writer import ScrapedVehicle, Target, write_vehicle  # noqa: E402

COUNTS = {
    "car_parts": "SELECT count(*) FROM car_parts WHERE car_id = %(c)s",
    "car_diagrams": "SELECT count(*) FROM car_diagrams WHERE car_id = %(c)s",
    "diagram_parts": "SELECT count(*) FROM diagram_parts dp JOIN car_diagrams cd ON cd.diagram_id = dp.diagram_id WHERE cd.car_id = %(c)s",
    "diagram_parts_index_sig": "SELECT md5(string_agg(p.part_number || ':' || dp.part_index, ',' ORDER BY p.part_number, dp.part_index)) FROM diagram_parts dp JOIN car_diagrams cd ON cd.diagram_id = dp.diagram_id JOIN part p ON p.id = dp.part_id WHERE cd.car_id = %(c)s",
    "diagrams_with_image": "SELECT count(*) FROM diagram d JOIN car_diagrams cd ON cd.diagram_id = d.id WHERE cd.car_id = %(c)s AND d.image_id IS NOT NULL",
    "category_sig": "SELECT md5(string_agg(coalesce(c.name,'') || '/' || coalesce(s.name,''), ',' ORDER BY c.name, s.name)) FROM diagram d JOIN car_diagrams cd ON cd.diagram_id = d.id LEFT JOIN category c ON c.id = d.category_id LEFT JOIN subcategory s ON s.id = d.sub_category_id WHERE cd.car_id = %(c)s",
    "part_title_sig": "SELECT md5(string_agg(p.part_number || ':' || coalesce(p.title,''), ',' ORDER BY p.part_number)) FROM car_parts cp JOIN part p ON p.id = cp.part_id WHERE cp.car_id = %(c)s",
}


def snapshot(cur, car_id):
    out = {}
    for name, sql in COUNTS.items():
        cur.execute(sql, {"c": car_id})
        out[name] = cur.fetchone()[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--target-car", type=int, required=True)
    a = ap.parse_args()

    conn = psycopg2.connect(os.environ["PARTS_INTERCHANGE_DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        "SELECT id, manufacturer_id, year, make, model, trim, engine, page_url FROM scrape_target WHERE car_id = %s",
        (a.target_car,),
    )
    t = Target(*cur.fetchone())
    print("target:", t)

    tree = json.load(open(os.path.join(a.data_dir, "tree.json")))
    node = tree[t.year]["makes"][t.make]["models"][t.model]["trims"][t.trim]["engines"][t.engine]
    wanted = set(node["parts"])
    parts = {}
    with open(os.path.join(a.data_dir, "parts.json"), "rb") as f:
        for pn, d in ijson.kvitems(f, ""):
            if pn in wanted:
                parts[pn] = d
                if len(parts) == len(wanted):
                    break
    imgs_all = json.load(open(os.path.join(a.data_dir, "imgs.json")))
    names = {dg.get("img") for e in node["diagrams"] for dg in e.get("diagrams", []) if dg.get("img")}
    for d in parts.values():
        for e in d.get("images", []) or []:
            for k in ("main", "preview", "thumb"):
                if e.get(k):
                    names.add(e[k].get("url", "").split("/")[-1])
    images = {n: {"url": imgs_all[n].get("url"), "alt": imgs_all[n].get("alt"), "saved": imgs_all[n].get("saved")}
              for n in names if n in imgs_all}
    print(f"raw: {len(node['parts'])} part numbers, {len(parts)} part pages, {len(images)} images")

    before = snapshot(cur, a.target_car)
    try:
        st = write_vehicle(conn, a.config, t, ScrapedVehicle(node["diagrams"], node["parts"], parts, images))
        after = snapshot(cur, st.car_id)
        print("write stats:", st)
        ok = st.car_id == a.target_car and not st.car_created
        for k in COUNTS:
            same = before[k] == after[k]
            ok &= same
            print(f"  {k:24} loader={before[k]!s:34} writer={after[k]!s:34} {'OK' if same else 'DIFF'}")
        print("EQUIVALENT" if ok else "NOT EQUIVALENT")
    finally:
        conn.rollback()
        print("rolled back")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
