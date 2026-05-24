# Running the Scraper

## Installation

```bash
cd pull_a_part_scraper
pip install -r requirements.txt
```

Python 3.10+ is required (uses `str | None` union syntax).

---

## One-off Run

```bash
python scraper.py
```

The database file `pull_a_part.db` is created next to `scraper.py` on the first run.
All tables are created automatically — no migration step needed.

To use a custom DB location:

```bash
python scraper.py --db /path/to/my_inventory.db
```

---

## What Happens on First Run

1. **Location sync** — fetches all Pull-A-Part yards (~50 locations, 1 request).
2. **Make sync** — fetches all vehicle makes (~70 makes, 1 request).
3. **Inventory sync** — sends one POST per make with all location IDs in the payload.
   This yields ~70 requests instead of the ~3,500 needed by the old one-location-per-make
   approach.  Expect ~1–2 minutes for this phase.
4. **Detail fetch** — fetches extended VIN data for every vehicle found in step 3.
   With thousands of vehicles this is the slow phase (~30–90 minutes on first run).
   **Progress is committed after every vehicle**, so the run is safe to interrupt
   and resume — already-fetched details will be skipped on the next run.

---

## What Happens on Subsequent Runs

Phases 1–3 are always executed (they are fast and keep the location/make/inventory tables
current).  Phase 4 only fetches details for vehicles that are new since the last run
(vehicles where `has_details = False`).  On a daily cadence with typical yard turnover
this is usually a few dozen vehicles — phase 4 completes in seconds.

---

## Scheduling with cron

Add a line to your crontab to run daily at 3 AM:

```cron
0 3 * * * /usr/bin/python3 /path/to/pull_a_part_scraper/scraper.py >> /path/to/scraper.log 2>&1
```

Or with a virtual environment:

```cron
0 3 * * * /path/to/venv/bin/python /path/to/pull_a_part_scraper/scraper.py >> /path/to/scraper.log 2>&1
```

---

## Rate Limiting

The scraper delays 0.5–1.0 seconds between every API request (randomised to avoid
fixed-interval detection).  Do not reduce these delays — a ban affects all scrapers
running from this IP.

---

## 429 / Rate-Limit Recovery

If the API returns a `429 Too Many Requests`, the scraper:

1. Writes the timestamp to `backoff.json` next to `scraper.py`.
2. Exits immediately — no automatic retry.
3. Subsequent runs abort at startup with a clear message until `backoff.json` is cleared.

To resume after a ban:

```bash
# Review the file
cat backoff.json

# Clear the affected domain (edit file) or remove it entirely
rm backoff.json

# Re-run
python scraper.py
```

---

## Checking Progress

```bash
# How many vehicles are in the DB
sqlite3 pull_a_part.db "SELECT COUNT(*) FROM vehicles WHERE active=1;"

# Still missing details
sqlite3 pull_a_part.db "SELECT COUNT(*) FROM vehicles WHERE active=1 AND has_details=0;"

# Last 5 runs
sqlite3 pull_a_part.db \
  "SELECT id, started_at, completed_at, vehicles_added, vehicles_removed, details_fetched, success \
   FROM scrape_runs ORDER BY id DESC LIMIT 5;"
```

---

## Output Files

| File             | Description                                      |
|------------------|--------------------------------------------------|
| `pull_a_part.db` | SQLite database with all inventory data          |
| `backoff.json`   | Created only if a 429 is received; delete to resume |

No JSONL or CSV output is produced — all data lives in the SQLite database.
See `docs/database_schema.md` for ready-to-use query examples.
