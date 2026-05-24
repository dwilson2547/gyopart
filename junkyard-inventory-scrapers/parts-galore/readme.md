# Parts Galore — Inventory Scraper

**Target:** https://parts-galore.com/inventory/

## Strategy

`static-html` — the full inventory table (`<table id="alldata">`) is embedded in the
initial page HTML. A single `requests` GET captures all ~1140 vehicles. No JavaScript
rendering required; no AJAX endpoints; the client-side JS only filters rows visually.

## Schema

| Column | Source | Notes |
|--------|--------|-------|
| `vin` | VIN cell | Dedup key — unique per recon |
| `year` | Year cell | Integer |
| `make` | Make cell | e.g. "Ford" |
| `model` | Model cell | e.g. "F-150" |
| `color` | Color cell | e.g. "WHITE" |
| `yard_date` | Yard Date cell | ISO date `YYYY-MM-DD` |
| `yard_row` | Row cell | Aisle/row number in yard |
| `first_seen_at` | Scraper | Set on first insert, never overwritten |
| `last_seen_at` | Scraper | Refreshed on every run where vehicle appears |
| `is_active` | Scraper | `False` when vehicle is no longer on the page |

## Running

```bash
# First run — creates inventory.db
python scraper.py

# Weekly re-run (recommended cadence)
python scraper.py
```

Each run logs: `new=N  updated=N  removed=N  total_in_feed=N`

Results are persisted to `inventory.db` (SQLite, SQLAlchemy ORM).

## Environment variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBCACHE_URL` | `http://webcache.scrapestack.local` | Web cache service URL |
| `WEBCACHE_TIMEOUT` | `30.0` | Seconds before cache request times out |
| `REQUEST_AUTH_SERVER_URL` | `request-auth-server.scrapestack.local:9000` | Rate-limit authority |
| `CACHE_MAX_AGE_SECONDS` | `82800` (23 h) | How long a cached page is considered fresh |
