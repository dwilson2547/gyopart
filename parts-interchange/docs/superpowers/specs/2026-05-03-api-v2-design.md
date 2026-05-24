# API v2 Design Spec
**Date:** 2026-05-03
**Location:** `api-v2/`

## Overview

Replace the existing Flask + CherryPy API with a FastAPI service. The new API serves the parts interchange UI, orchestrates OEM parts scraper jobs via Apache Iggy, and provides the data foundation for future junkyard inventory integration.

## Stack

- **FastAPI** + Uvicorn (replaces Flask + CherryPy)
- **SQLAlchemy 2.0 async** + asyncpg (replaces sync SQLAlchemy + psycopg2)
- **Pydantic v2** (replaces hand-rolled `Validator` class)
- **Apache Iggy Python SDK** (job queue for OEM parts scraper)
- **Python 3.12+**
- **PostgreSQL** (existing instance, schema extended)

## Project Structure

```
api-v2/
  src/
    main.py               # FastAPI app, lifespan (DB pool + Iggy connection)
    config.py             # Pydantic settings, loaded from env vars
    database.py           # Async engine, session dependency
    models/
      vehicle.py          # Year, Make, Model, Trim, Engine, Car ORM models
      parts.py            # Part, Image, Diagram, Category, SubCategory ORM models
      junkyard.py         # Junkyard, ScrapeConfig, ScrapeJob, JunkyardInventory ORM models
    routers/
      vehicles.py         # GET /v1/vehicles/...
      parts.py            # GET /v1/parts/...
      junkyards.py        # GET /v1/junkyards/...
      feedback.py         # POST /v1/feedback
      admin/
        junkyards.py      # CRUD /v1/admin/junkyards
        scrape.py         # /v1/admin/scrape-configs + scrape-jobs
      worker/
        parts.py          # /v1/worker/... (OEM parts scraper callbacks)
    schemas/
      vehicle.py          # Pydantic request/response models
      parts.py
      junkyard.py
      admin.py
      worker.py
    services/
      iggy.py             # Iggy client wrapper, publish_scrape_job()
      geo.py              # Haversine distance calculation
    middleware/
      auth.py             # API key dependencies: require_admin_key, require_worker_key
  requirements.txt
  dockerfile
```

## Authentication

Two separate API keys, configured via environment variables:

- `X-Admin-Key` — required on all `/v1/admin/` routes
- `X-Worker-Key` — required on all `/v1/worker/` routes

Keys are independent so worker credentials can be rotated without affecting the admin panel.

## API Routes

All routes versioned under `/v1`.

### Vehicle Cascade
```
GET /v1/vehicles/years
GET /v1/vehicles/makes?year_id=
GET /v1/vehicles/models?year_id=&make_id=
GET /v1/vehicles/trims?year_id=&make_id=&model_id=
GET /v1/vehicles/engines?year_id=&make_id=&model_id=&trim_id=
GET /v1/vehicles/cars?year_id=&make_id=&model_id=&trim_id=&engine_id=
```

### Parts
```
GET /v1/parts?car_id=&page=&per_page=&sort=&filter=
GET /v1/parts/{part_id}
GET /v1/parts/{part_id}/compatible-cars?page=&per_page=
```

### Junkyards
```
GET /v1/junkyards?part_id=&lat=&lng=&radius_miles=&page=&per_page=
```
Resolves `part_id` → compatible cars → matching junkyard inventory. Sorted by distance when `lat`/`lng` provided, otherwise by inventory recency.

### Misc
```
GET  /v1/manufacturers
POST /v1/feedback
```

### Admin (X-Admin-Key required)
```
GET    /v1/admin/junkyards
POST   /v1/admin/junkyards
PUT    /v1/admin/junkyards/{id}
DELETE /v1/admin/junkyards/{id}

GET    /v1/admin/scrape-configs
POST   /v1/admin/scrape-configs
PUT    /v1/admin/scrape-configs/{id}
DELETE /v1/admin/scrape-configs/{id}
POST   /v1/admin/scrape-configs/{id}/trigger   # manual scrape kick-off

GET    /v1/admin/scrape-jobs                   # job history and status
```

### Worker (X-Worker-Key required)
```
PUT  /v1/worker/scrape-jobs/{id}/status        # pending → running → completed/failed
POST /v1/worker/parts                          # upsert a batch of parts
POST /v1/worker/images                         # upsert a batch of images
POST /v1/worker/cars                           # upsert a batch of car/vehicle records
```

Worker endpoints are the write path for the OEM parts scraper. The scraper reads the database directly (read-only credentials) for deduplication at volume, then calls these endpoints only for new or updated records.

## Iggy Integration

**Stream:** `parts-interchange`
**Topics:**
- `scrape-jobs` — API publishes, OEM parts scraper worker consumes
- `scrape-results` — reserved for future use (not required for v1)

### Scrape Job Message Schema
```json
{
  "job_id": 42,
  "scrape_site_config_id": 7,
  "site_type": "acura",
  "url": "https://www.acuraoempartsdirect.com",
  "triggered_by": "scheduler | admin"
}
```

### Flow
1. Admin triggers via `POST /v1/admin/scrape-configs/{id}/trigger` (or scheduler)
2. API inserts `scrape_job` row with `status = pending`
3. API publishes `ScrapeJobCreated` message to `scrape-jobs` topic
4. Returns `job_id` immediately — non-blocking
5. Worker consumes job from Iggy (queue serializes naturally if only one worker running)
6. Worker calls `PUT /v1/worker/scrape-jobs/{id}/status` → `running`
7. Worker reads DB directly to check for existing records (deduplication)
8. Worker calls `POST /v1/worker/parts|images|cars` for new/updated records only
9. Worker calls `PUT /v1/worker/scrape-jobs/{id}/status` → `completed` or `failed`

`services/iggy.py` wraps the Iggy Python SDK with a lifespan-managed async connection and a single `publish_scrape_job(job_id, config)` method.

## Database Changes

### Existing tables
All existing tables are preserved with no breaking changes. Existing data is not migrated.

**Columns removed from `part`** (empty across all 2.6M rows, never populated):
- `replaces`
- `notes`

**`part.positions`** — migrated from `TEXT` to `TEXT[]`. Existing comma-separated values split on first load. Enables `@>` containment queries.

**`part.applications`** — HTML-stripped at the API response layer (not at DB level). Can be cleaned in a future loader pass.

### New tables

```sql
CREATE TABLE junkyard (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    address    TEXT,
    city       TEXT,
    state      TEXT,
    zip        TEXT,
    lat        DOUBLE PRECISION,
    lng        DOUBLE PRECISION,
    phone      TEXT,
    website    TEXT,
    active     BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scrape_site_config (
    id                    SERIAL PRIMARY KEY,
    junkyard_id           INTEGER REFERENCES junkyard(id),
    site_type             TEXT NOT NULL,
    url                   TEXT NOT NULL,
    scrape_interval_hours INTEGER DEFAULT 24,
    enabled               BOOLEAN DEFAULT TRUE,
    last_scraped_at       TIMESTAMPTZ,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scrape_job (
    id                    SERIAL PRIMARY KEY,
    scrape_site_config_id INTEGER REFERENCES scrape_site_config(id),
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    error_message         TEXT
);

CREATE TABLE junkyard_inventory (
    id            SERIAL PRIMARY KEY,
    junkyard_id   INTEGER REFERENCES junkyard(id) NOT NULL,
    scrape_job_id INTEGER REFERENCES scrape_job(id),
    year          TEXT NOT NULL,
    make_name     TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    trim_name     TEXT,
    date_listed   DATE,
    date_removed  DATE,
    price         NUMERIC(10,2),
    row_location  TEXT,
    vin           TEXT,
    raw_data      JSONB,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

### Indexes for junkyard matching and deduplication
```sql
CREATE INDEX ON junkyard_inventory (junkyard_id, year, LOWER(make_name), LOWER(model_name));
CREATE INDEX ON junkyard_inventory (vin) WHERE vin IS NOT NULL;
```

## Junkyard Matching Strategy

When a user queries `/v1/junkyards?part_id=`:
1. Resolve compatible cars via `car_parts` junction → list of `(year.name, make.name, model.name)` tuples
2. Query `junkyard_inventory` using `LOWER(TRIM(...))` equality on year/make/model
3. Trim and engine are intentionally ignored — approximate matching is acceptable
4. Group results by junkyard, compute distance via Haversine if `lat`/`lng` provided
5. Sort by distance ascending (proximity) or `created_at` descending (recency) as fallback

## Proximity Search

Lat/lng stored as `DOUBLE PRECISION` floats on the `junkyard` table. Haversine formula computed in `services/geo.py` and applied in Python after the DB query (not in SQL). No PostGIS dependency — can be added later if dataset size warrants geographic indexing.

## What's Dropped

- `/load/<make>` — already deprecated; belongs in loader tooling, not the API
- `/mfr/` write endpoints — manufacturers are loader-managed; only `GET /v1/manufacturers` is kept
- `POST`-for-fetch pattern — all read operations use `GET`
- `page += 1` hack — clients send 1-based page numbers
- Flask, CherryPy, PyMySQL dependencies

## Out of Scope

- Junkyard inventory scraper worker design (TBD, separate session)
- Frontend admin panel UI (TBD)
- User accounts (explicitly excluded — no data privacy surface)
