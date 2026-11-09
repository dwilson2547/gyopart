"""Write one scraped vehicle into parts_interchange in a single transaction (design-v2 §3.5).

Field mapping mirrors parts-loader-v2's generate_csvs.py exactly — title cleaning, HTML stripping,
category parsing from the category link, merged part indices — so rows written here are
indistinguishable from bulk-loaded ones. Upserts use the 0.3.0 unique keys:
  car (manufacturer, year, make, model, trim, engine) · part (manufacturer, part_number)
  image (manufacturer, name)
Parts and images are shared across a manufacturer's cars and only ever upserted. The car's own link
sets are replaced: car_parts becomes exactly this scrape's parts, and its diagrams (which belong to
one car) are deleted and re-inserted.

The caller passes an open psycopg2 connection and owns the transaction (commit/rollback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import StringIO
from typing import Optional

from psycopg2.extras import execute_values


# ── value cleaning, ported from parts-loader-v2/src/generate_csvs.py ────────────────────────────


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.convert_charrefs = True
        self._buf = StringIO()

    def handle_data(self, d):
        self._buf.write(d)


def strip_html(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    h = _Stripper()
    h.feed(s)
    return h._buf.getvalue()


def clean_title(title: str, part_num: str) -> str:
    try:
        cleaned = "-".join(title.replace(part_num, "").split("-")[:-1]).strip()
        return cleaned or title
    except Exception:
        return title


def as_text(v):
    """The loader wrote values through csv.writer, i.e. str() of non-strings; keep that shape."""
    if v is None or isinstance(v, str):
        return v
    return str(v)


def parse_category(category_url: str) -> tuple[Optional[str], Optional[str]]:
    tail = category_url.rstrip("/").split("/")[-1]
    if not tail:
        tail = category_url.rstrip("/").split("/")[-2] if "/" in category_url.rstrip("/") else ""
    cats = tail.split("--")
    if len(cats) == 2:
        return cats[0].strip(), cats[1].strip()
    if cats and cats[0].strip():
        return cats[0].strip(), None
    return None, None


# ── input ───────────────────────────────────────────────────────────────────────────────────────


@dataclass
class Target:
    id: int
    manufacturer_id: int
    year: str
    make: str
    model: str
    trim: Optional[str]
    engine: Optional[str]
    page_url: Optional[str]


@dataclass
class ScrapedVehicle:
    """What the crawl collected for one vehicle — the same shapes tree.json / parts.json held."""
    diagrams: list[dict]                       # entries like engine["diagrams"]: {"diagrams": [diag, ...]}
    part_numbers: list[str]                    # engine["parts"]
    parts: dict[str, dict]                     # part_number -> parsed part page (parts.json entry)
    images: dict[str, dict] = field(default_factory=dict)  # name -> {"url", "alt", "saved", "uploaded", "content_hash"}


@dataclass
class WriteStats:
    car_id: int = 0
    car_created: bool = False
    parts_new: int = 0
    parts_updated: int = 0
    images: int = 0
    diagrams: int = 0
    car_parts: int = 0


class LookupMissing(Exception):
    """A select value has no lookup row. Discovery creates them (with display names) before a target
    is queued, so this means the target and the catalogue disagree."""


# ── lookups ─────────────────────────────────────────────────────────────────────────────────────


def _one(cur, sql: str, params: tuple) -> Optional[int]:
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def resolve_vehicle(cur, t: Target) -> tuple[int, int, int, Optional[int], Optional[int]]:
    year_id = _one(cur, "SELECT id FROM year WHERE name = %s", (t.year,))
    make_id = _one(cur, "SELECT id FROM make WHERE select_value = %s", (t.make,))
    model_id = (
        _one(cur, "SELECT id FROM model WHERE make_id = %s AND select_value = %s", (make_id, t.model))
        if make_id else None
    )
    trim_id = _one(cur, "SELECT id FROM trim WHERE select_value = %s", (t.trim,)) if t.trim else None
    engine_id = _one(cur, "SELECT id FROM engine WHERE select_value = %s", (t.engine,)) if t.engine else None
    missing = [n for n, v in (("year", year_id), ("make", make_id), ("model", model_id)) if v is None]
    if t.trim and trim_id is None:
        missing.append("trim")
    if t.engine and engine_id is None:
        missing.append("engine")
    if missing:
        raise LookupMissing(f"target {t.id}: no lookup row for {', '.join(missing)}")
    return year_id, make_id, model_id, trim_id, engine_id


def category_ids(cur, main: Optional[str], sub: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not main:
        return None, None
    cur.execute("INSERT INTO category (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (main,))
    cat_id = _one(cur, "SELECT id FROM category WHERE name = %s", (main,))
    if not sub:
        return cat_id, None
    cur.execute(
        "INSERT INTO subcategory (name, category_id) VALUES (%s, %s) "
        "ON CONFLICT ON CONSTRAINT uq_subcategory_category_name DO NOTHING",
        (sub, cat_id),
    )
    sub_id = _one(cur, "SELECT id FROM subcategory WHERE category_id = %s AND name = %s", (cat_id, sub))
    return cat_id, sub_id


# ── the write ───────────────────────────────────────────────────────────────────────────────────


def write_vehicle(conn, config_name: str, t: Target, v: ScrapedVehicle) -> WriteStats:
    st = WriteStats()
    mfr = t.manufacturer_id
    with conn.cursor() as cur:
        year_id, make_id, model_id, trim_id, engine_id = resolve_vehicle(cur, t)

        # 1. the car
        cur.execute(
            """
            INSERT INTO car (year_id, make_id, model_id, trim_id, engine_id, manufacturer_id, base_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_car_vehicle
              DO UPDATE SET base_url = COALESCE(EXCLUDED.base_url, car.base_url)
            RETURNING id, (xmax = 0)
            """,
            (year_id, make_id, model_id, trim_id, engine_id, mfr, t.page_url),
        )
        st.car_id, st.car_created = cur.fetchone()

        # 2. images (diagram and part images collected during the crawl)
        image_ids: dict[str, int] = {}
        if v.images:
            rows = [
                (name, f"{config_name}/images/{name}", meta.get("url"), meta.get("alt"),
                 bool(meta.get("saved", False)), bool(meta.get("uploaded", False)), meta.get("content_hash"), mfr)
                for name, meta in v.images.items()
            ]
            got = execute_values(
                cur,
                """
                INSERT INTO image (name, bucket_path, url, alt_text, saved, uploaded, content_hash, manufacturer_id)
                VALUES %s
                ON CONFLICT ON CONSTRAINT uq_image_manufacturer_name DO UPDATE SET
                  url = COALESCE(EXCLUDED.url, image.url),
                  alt_text = COALESCE(EXCLUDED.alt_text, image.alt_text),
                  saved = image.saved OR EXCLUDED.saved,
                  uploaded = image.uploaded IS TRUE OR EXCLUDED.uploaded,
                  content_hash = COALESCE(EXCLUDED.content_hash, image.content_hash)
                RETURNING name, id
                """,
                rows, fetch=True,
            )
            image_ids = dict(got)
            st.images = len(image_ids)

        # 3. parts — every part number on the car; a part page that failed still needs a row to link
        part_ids: dict[str, int] = {}
        numbers = list(dict.fromkeys(v.part_numbers))
        if numbers:
            full, minimal = [], []
            for pn in numbers:
                d = v.parts.get(pn)
                if d and not d.get("skipped"):
                    full.append((
                        d.get("url"), pn, mfr, (clean_title(d.get("title", "") or "", pn) or "")[:200],
                        as_text(d.get("also_known_as")), strip_html(d.get("description")),
                        as_text(d.get("positions")), as_text(d.get("notes")), d.get("msrp"),
                        as_text(d.get("applications")), d.get("is_hazmat"),
                        as_text(d.get("superseded_part_numbers")),
                    ))
                else:
                    minimal.append(((d or {}).get("url"), pn, mfr))
            if full:
                got = execute_values(
                    cur,
                    """
                    INSERT INTO part (url, part_number, manufacturer_id, title, other_names, description,
                                      positions, notes, msrp, applications, hazmat, replaces) VALUES %s
                    ON CONFLICT ON CONSTRAINT uq_part_manufacturer_number DO UPDATE SET
                      url = EXCLUDED.url, title = EXCLUDED.title, other_names = EXCLUDED.other_names,
                      description = EXCLUDED.description, positions = EXCLUDED.positions,
                      notes = EXCLUDED.notes, msrp = EXCLUDED.msrp,
                      applications = EXCLUDED.applications, hazmat = EXCLUDED.hazmat,
                      replaces = COALESCE(EXCLUDED.replaces, part.replaces)
                    RETURNING part_number, id, (xmax = 0)
                    """,
                    full, fetch=True,
                )
                for pn, pid, created in got:
                    part_ids[pn] = pid
                    st.parts_new += created
                    st.parts_updated += not created
            if minimal:
                # Page failed this time: keep whatever the row already holds.
                got = execute_values(
                    cur,
                    """
                    INSERT INTO part (url, part_number, manufacturer_id, title) VALUES %s
                    ON CONFLICT ON CONSTRAINT uq_part_manufacturer_number
                      DO UPDATE SET part_number = part.part_number
                    RETURNING part_number, id, (xmax = 0)
                    """,
                    [(u, pn, m, "") for u, pn, m in minimal], fetch=True,
                )
                for pn, pid, created in got:
                    part_ids[pn] = pid
                    st.parts_new += created

            # part images
            pi_rows = []
            for pn, d in v.parts.items():
                pid = part_ids.get(pn)
                if not pid or not d or d.get("skipped"):
                    continue
                seen = set()
                for entry in d.get("images", []) or []:
                    for key in ("main", "preview", "thumb"):
                        obj = entry.get(key)
                        name = (obj or {}).get("url", "").split("/")[-1] if obj else ""
                        if not name or name in seen or name not in image_ids:
                            continue
                        pi_rows.append((pid, image_ids[name], entry.get("caption")))
                        seen.add(name)
            if pi_rows:
                execute_values(
                    cur,
                    "INSERT INTO part_images (part_id, image_id, part_image_text) VALUES %s "
                    "ON CONFLICT (part_id, image_id) DO UPDATE SET part_image_text = EXCLUDED.part_image_text",
                    pi_rows,
                )

        # 4. replace the car's link sets
        cur.execute("DELETE FROM car_parts WHERE car_id = %s", (st.car_id,))
        if part_ids:
            execute_values(cur, "INSERT INTO car_parts (car_id, part_id) VALUES %s ON CONFLICT DO NOTHING",
                           [(st.car_id, pid) for pid in part_ids.values()])
            st.car_parts = len(part_ids)

        cur.execute("SELECT diagram_id FROM car_diagrams WHERE car_id = %s", (st.car_id,))
        old = [r[0] for r in cur.fetchall()]
        if old:
            cur.execute("DELETE FROM diagram_parts WHERE diagram_id = ANY(%s)", (old,))
            cur.execute("DELETE FROM car_diagrams WHERE car_id = %s", (st.car_id,))
            # Only delete diagrams no other car links to (the loader never shared them; be safe).
            cur.execute(
                "DELETE FROM diagram d WHERE d.id = ANY(%s) "
                "AND NOT EXISTS (SELECT 1 FROM car_diagrams cd WHERE cd.diagram_id = d.id)",
                (old,),
            )

        wanted = set(numbers)
        for entry in v.diagrams:
            for diag in entry.get("diagrams", []):
                if diag.get("skipped"):
                    continue
                img = diag.get("img") or ""
                cat_id, sub_id = category_ids(cur, *parse_category(diag.get("category_link", "")))
                cur.execute(
                    "INSERT INTO diagram (image_id, category_id, sub_category_id, base_car_url, category_url) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (image_ids.get(img) if img else None, cat_id, sub_id,
                     diag.get("base_car_url"), diag.get("category_link")),
                )
                diag_id = cur.fetchone()[0]
                cur.execute("INSERT INTO car_diagrams (car_id, diagram_id) VALUES (%s, %s)", (st.car_id, diag_id))
                st.diagrams += 1
                index_map: dict[int, str] = {}
                for idx, pnums in (diag.get("parts") or {}).items():
                    for pn in pnums:
                        pid = part_ids.get(pn) if pn in wanted else None
                        if pid is None:
                            continue
                        idx_clean = idx.strip()
                        if pid in index_map:
                            if idx_clean not in index_map[pid].split(","):
                                index_map[pid] += "," + idx_clean
                        else:
                            index_map[pid] = idx_clean
                if index_map:
                    execute_values(
                        cur,
                        "INSERT INTO diagram_parts (diagram_id, part_id, part_index) VALUES %s",
                        [(diag_id, pid, ix[:25]) for pid, ix in index_map.items()],
                    )

        # 5. the target
        cur.execute(
            "UPDATE scrape_target SET status = 'done', car_id = %s, last_scraped_at = now() AT TIME ZONE 'utc', "
            "attempts = 0, last_error = NULL, next_attempt_at = NULL WHERE id = %s",
            (st.car_id, t.id),
        )
    return st
