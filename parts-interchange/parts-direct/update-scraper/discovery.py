"""Discovery: find vehicles the site lists that the queue doesn't know yet (design-v2 §3.2, step 2).

Walks the site's vehicle picker — newest model year first — and upserts every vehicle into
scrape_target; unknown ones arrive as `pending`, which the queue serves before anything stale, so new
vehicles are scraped first. Runs at the start of a run when the manufacturer's last *complete* pass is
older than DISCOVERY_INTERVAL_DAYS (✅ 90, user 2026-10-11). Upserts commit as it goes, so a pass cut off
by the deadline keeps what it found; only a complete pass resets the clock (a `scrape_run` row named
"<config>:discovery", so no schema change).

The picker's AJAX endpoints answer 403 until the session has made one top-level navigation to the
makes endpoint (found 2026-10-11), so the pass starts there, then returns to the homepage for the CSRF
token the picker requires.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import psycopg2

from recent_tree_builder import RecentTreeBuilder
from utils.Constants import Steps

import work_queue as q

DISCOVERY_INTERVAL_DAYS = 90

# Some pickers list other brands, whose pages only sell aftermarket parts (they redirect to
# ?brandType=aftermarket). Mopar flags its own makes with `primary_make`; the Toyota dealer site lists 18
# makes and flags none, so it is named here (checked 2026-10-13). Single-family sites (GM, Ford, Hyundai,
# Jaguar) list only their own brands and flag none.
OEM_MAKES = {"toyota": {"toyota", "scion"}}


def oem_makes(config: str, makes: list[dict]) -> list[dict]:
    if config in OEM_MAKES:
        return [m for m in makes if m["url"] in OEM_MAKES[config]]
    primary = [m for m in makes if m.get("primary_make")]
    return primary or makes


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_name(config: str) -> str:
    return f"{config}:discovery"


def due(cur, config: str, interval_days: int = DISCOVERY_INTERVAL_DAYS) -> bool:
    cur.execute("SELECT max(completed_at) FROM scrape_run WHERE manufacturer = %s AND success",
                (run_name(config),))
    last = cur.fetchone()[0]
    return last is None or last < utcnow() - timedelta(days=interval_days)


def record(cur, config: str, started: datetime, found: int, new: int) -> None:
    cur.execute(
        """INSERT INTO scrape_run (manufacturer, started_at, completed_at, cars_processed, new_parts,
                                   updated_parts, success, error_message)
           VALUES (%s, %s, %s, %s, 0, 0, true, %s)""",
        (run_name(config), started, utcnow(), found, f"discovery: {found} vehicles listed, {new} new"),
    )


def _id(cur, sql: str, params: tuple):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


class Lookups:
    """Create the year/make/model/trim/engine rows a discovered vehicle needs, with the picker's display
    names, so the writer can resolve it (writer.resolve_vehicle). Trims and engines are shared across
    manufacturers and have no unique key, so creation takes a transaction-scoped advisory lock against
    a parallel run of another manufacturer adding the same value."""

    LOCK = 7261_0001

    def __init__(self):
        self._seen: set[tuple] = set()

    def ensure(self, cur, year: str, make: dict, model: dict, trim: dict, engine: dict) -> None:
        key = (year, make["url"], model["url"], trim["url"], engine["url"])
        if key in self._seen:
            return
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (self.LOCK,))
        if _id(cur, "SELECT id FROM year WHERE name = %s", (year,)) is None:
            cur.execute("INSERT INTO year (name) VALUES (%s)", (year,))
        make_id = _id(cur, "SELECT id FROM make WHERE select_value = %s", (make["url"],))
        if make_id is None:
            make_id = _id(cur, "INSERT INTO make (name, select_value, start_year, end_year) "
                               "VALUES (%s, %s, %s, %s) RETURNING id",
                          (make["ui"], make["url"], make.get("start_year"), make.get("end_year")))
        cur.execute("INSERT INTO model (name, select_value, make_id) VALUES (%s, %s, %s) "
                    "ON CONFLICT ON CONSTRAINT uq_model_make_select DO NOTHING",
                    (model["ui"], model["url"], make_id))
        for table, item in (("trim", trim), ("engine", engine)):
            if _id(cur, f"SELECT id FROM {table} WHERE select_value = %s", (item["url"],)) is None:
                cur.execute(f"INSERT INTO {table} (name, select_value) VALUES (%s, %s)", (item["ui"], item["url"]))
        self._seen.add(key)


class Discovery:
    def __init__(self, updater, conn, mfr_id: int, out_of_time: Callable[[], bool]):
        self.u = updater
        self.conn = conn
        self.mfr_id = mfr_id
        self.out_of_time = out_of_time
        self.found = self.new = self.skipped = 0
        self.lookups = Lookups()

    def run(self, current_year: Optional[int] = None) -> bool:
        """True if the pass completed. Raises on site/VPN trouble like any page fetch."""
        started = utcnow()
        base = self.u.base_url
        builder = RecentTreeBuilder(base, years_to_refresh=self.u.discovery_years,
                                    request_auth=self.u.request_auth,
                                    current_year=current_year)
        # Warm-up: a top-level navigation to the makes endpoint (its JSON is the page body).
        self.u._navigate(builder.ALL_MAKES_URL)
        makes = oem_makes(self.u.config_name, json.loads(self.u._page.inner_text("body")))
        self.u._navigate(base)
        builder.csrf_token = self.u._page.evaluate(
            "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || null")

        # Next model year too: sites list it months before the calendar catches up.
        top = builder.current_year + 1
        years = range(top, builder.minimum_year - 1, -1)
        page = self.u._page
        for year in years:
            year_new = 0
            for make in makes:
                if not (make["start_year"] <= year <= make["end_year"]):
                    continue
                for model in builder._fetch_options(builder._build_params(Steps.MODEL, str(year), make["url"]),
                                                    page=page) or []:
                    for trim in builder._fetch_options(
                            builder._build_params(Steps.TRIM, str(year), make["url"], model["url"]), page=page) or []:
                        engines = builder._fetch_options(
                            builder._build_params(Steps.ENGINE, str(year), make["url"], model["url"], trim["url"]),
                            page=page) or []
                        with self.conn.cursor() as cur:
                            for engine in engines:
                                url = builder._build_car_url(year, make["url"], model["url"], trim["url"],
                                                             engine["url"])
                                # One vehicle whose lookups can't be created must not end the pass: a
                                # trim name already stored under another slug ("Empower+", uq_trim_name)
                                # stopped every Nissan discovery at 2026 (2026-10-13).
                                cur.execute("SAVEPOINT vehicle")
                                try:
                                    self.lookups.ensure(cur, str(year), make, model, trim, engine)
                                    is_new = q.upsert_discovered(cur, self.mfr_id, str(year), make["url"],
                                                                 model["url"], trim["url"], engine["url"], url)
                                except psycopg2.IntegrityError as ex:
                                    cur.execute("ROLLBACK TO SAVEPOINT vehicle")
                                    self.skipped += 1
                                    print(f"discovery: skipped {url}: {str(ex).splitlines()[-1].strip()}", flush=True)
                                    continue
                                cur.execute("RELEASE SAVEPOINT vehicle")
                                self.found += 1
                                self.new += is_new
                                year_new += is_new
                        self.conn.commit()
                    if self.out_of_time():
                        print(f"discovery: out of time in {year}; {self.found} listed, {self.new} new so far",
                              flush=True)
                        return False
            print(f"discovery: {year} done, {year_new} new", flush=True)
        with self.conn.cursor() as cur:
            record(cur, self.u.config_name, started, self.found, self.new)
        self.conn.commit()
        print(f"discovery complete: {self.found} vehicles listed, {self.new} new, {self.skipped} skipped", flush=True)
        return True
