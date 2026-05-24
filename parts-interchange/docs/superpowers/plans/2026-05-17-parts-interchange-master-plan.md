# Parts Interchange — Master Roadmap

> **For agentic workers:** This is a master roadmap, not an execution plan. Each phase has a linked sub-plan that contains the actual step-by-step implementation tasks. Write the sub-plan just-in-time when that phase begins. Use `superpowers:writing-plans` to produce each sub-plan and `superpowers:subagent-driven-development` to execute it.

**Goal:** Transform the parts-interchange system from a static data POC into a live, end-to-end platform where a user picks their car and part, then sees which nearby junkyards have compatible vehicles in stock.

**Final User Flow:**
1. User selects vehicle + part on parts-interchange UI
2. System resolves all compatible car IDs via `car_parts` interchange table
3. System queries junkyard inventory for those car IDs within a radius
4. UI shows a ranked list of nearby yards with match counts and vehicle details

**Architecture:**
- One PostgreSQL cluster, two schemas: `parts_interchange` (parts catalog) and `junkyard_inventory` (yard data + mapping pipeline)
- All junkyard scrapers run on k8s cron schedules, write to the shared postgres via the common schema
- parts-direct scraper re-architected to write to both webcache/imgcache and postgres in a single pass
- Vehicle-to-car mapping pipeline runs post-scrape to link junkyard vehicles to parts-interchange car IDs
- FastAPI backend (api-v2 replacement, written fresh) serves both parts search and junkyard inventory search
- React/Vite frontend (ui-v2 replacement, written fresh) integrates both flows

**Tech Stack:** Python, FastAPI, SQLAlchemy (Core for bulk ops, ORM for queries), Alembic, PostgreSQL, React/Vite, TypeScript, Docker, Kubernetes, Helm, GitHub Actions

---

## Architecture Decisions (Locked)

| Decision | Rationale |
|---|---|
| `VehicleDetail` table eliminated | Flattened into `Vehicle` table. Structured columns (trim, engine, drivetrain) move directly onto `Vehicle`. Yard-specific overflow goes in `extras JSON` on `Vehicle`. |
| Single Postgres, two schemas | Simplifies inventory search (no HTTP bridge between DBs). Schema `junkyard_inventory` for scraper data; schema `parts_interchange` for parts catalog. |
| parts-direct scraper writes cache + DB in one pass | No separate loader for new scrape runs. Scraper routes all HTTP through webcache/imgcache, writes structured data to postgres on the same run. parts-loader-v2 still used for the existing ~1TB tarball ingestion only. |
| api-v2 and ui-v2 are discarded | Both are POCs with schema drift from the canonical junkyard schema. Fresh implementations written against the finalized schemas. |
| VIN is primary deduplication key | NHTSA decode is free, offline, reliable post-1980. pre-1984 vehicles → `no_match_in_dataset`, not an error. |
| LLM creates rule suggestions, not direct resolutions | Rules are auditable, reusable, correctable. Direct resolutions are not. All LLM rules require human approval. |
| Manual override available | Admin can directly assign `car_id` on any vehicle; creates a `MappingDiscrepancy` with `status="manual"`. |

---

## Canonical Junkyard Vehicle Schema

This is the **finalized schema** all sub-plans must use. VehicleDetail is gone.

```python
# junkyard_inventory schema

class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("source", "source_location_id"),)
    id                 = Column(Integer, primary_key=True)
    source             = Column(String(100), nullable=False, index=True)
    source_location_id = Column(String(100), nullable=False)
    name               = Column(String(200), nullable=False)
    chain              = Column(String(100), nullable=True)
    address            = Column(String(500), nullable=True)
    city               = Column(String(100), nullable=True)
    state              = Column(String(10),  nullable=True)
    zip_code           = Column(String(20),  nullable=True)
    phone              = Column(String(50),  nullable=True)
    lat                = Column(Float,       nullable=True)
    lng                = Column(Float,       nullable=True)
    is_active          = Column(Boolean,     nullable=False, default=True)
    first_seen_at      = Column(DateTime,    nullable=False)
    last_seen_at       = Column(DateTime,    nullable=False)

class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("source", "source_key"),)
    id          = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    source      = Column(String(100), nullable=False, index=True)
    source_key  = Column(String(200), nullable=False)

    # Core identity
    year  = Column(Integer,     nullable=True)
    make  = Column(String(100), nullable=True)
    model = Column(String(200), nullable=True)
    vin   = Column(String(17),  nullable=True, index=True)
    row   = Column(String(20),  nullable=True)
    arrival_date = Column(DateTime, nullable=True)
    color = Column(String(100), nullable=True)

    # Formerly VehicleDetail (flattened in)
    trim               = Column(String(200), nullable=True)
    vehicle_type       = Column(String(100), nullable=True)  # Car/Truck/SUV
    body_type          = Column(String(100), nullable=True)
    body_sub_type      = Column(String(100), nullable=True)
    doors              = Column(Integer,     nullable=True)
    style              = Column(String(200), nullable=True)
    drive_type         = Column(String(50),  nullable=True)  # FWD/RWD/AWD/4WD
    fuel_type          = Column(String(50),  nullable=True)  # G/D/E/H
    engine_block       = Column(String(10),  nullable=True)  # I/V/H
    engine_cylinders   = Column(Integer,     nullable=True)
    engine_size        = Column(Float,       nullable=True)   # litres
    engine_aspiration  = Column(String(50),  nullable=True)  # N/A or T
    trans_type         = Column(String(10),  nullable=True)  # A/M/CVT
    trans_speeds       = Column(Integer,     nullable=True)
    mileage            = Column(Integer,     nullable=True)
    preview_image_url  = Column(String(500), nullable=True)
    detail_fetched_at  = Column(DateTime,    nullable=True)
    extras             = Column(JSON,        nullable=True)  # yard-specific overflow

    # Car-ID mapping (populated by resolution pipeline)
    car_id            = Column(Integer,     nullable=True, index=True)  # FK to parts_interchange.car.id
    car_id_resolved   = Column(Boolean,     nullable=False, default=False)
    car_id_method     = Column(String(20),  nullable=True)  # vin_decode|ymmt_match|manual|rule_applied
    car_id_confidence = Column(Float,       nullable=True)  # 1.0=VIN, <1.0=fuzzy/rule

    # Bookkeeping
    is_active     = Column(Boolean,  nullable=False, default=True)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at  = Column(DateTime, nullable=False)

class MappingRule(Base):
    __tablename__ = "mapping_rules"
    id             = Column(Integer,   primary_key=True)
    scope          = Column(String(20), nullable=False)   # global|source|location
    source         = Column(String(100), nullable=True)
    location_id    = Column(Integer,   ForeignKey("locations.id"), nullable=True)
    field          = Column(String(50), nullable=False)   # make|model|trim
    rule_type      = Column(String(20), nullable=False)   # exact|prefix|regex
    raw_value      = Column(String(200), nullable=False)
    canonical_value = Column(String(200), nullable=False)
    make_context   = Column(String(100), nullable=True)
    priority       = Column(Integer,   default=100)
    is_active      = Column(Boolean,   default=True)
    created_by     = Column(String(20), nullable=False)   # manual|llm_suggested|import
    created_at     = Column(DateTime,  nullable=False)
    applied_count  = Column(Integer,   default=0)
    llm_confidence = Column(Float,     nullable=True)
    llm_rationale  = Column(String(1000), nullable=True)
    approved_at    = Column(DateTime,  nullable=True)
    approved_by    = Column(String(100), nullable=True)

class MappingDiscrepancy(Base):
    __tablename__ = "mapping_discrepancies"
    id         = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), unique=True, nullable=False)
    raw_year   = Column(String(20),  nullable=True)
    raw_make   = Column(String(100), nullable=True)
    raw_model  = Column(String(200), nullable=True)
    raw_trim   = Column(String(200), nullable=True)
    fuzzy_make_match  = Column(String(100), nullable=True)
    fuzzy_make_score  = Column(Float,       nullable=True)
    fuzzy_model_match = Column(String(200), nullable=True)
    fuzzy_model_score = Column(Float,       nullable=True)
    candidate_car_id  = Column(Integer,     nullable=True)
    status = Column(String(30), nullable=False, default="unresolved")
    # unresolved | pending_rule | rule_applied | manual | ignored | no_match_in_dataset
    resolved_car_id     = Column(Integer,  nullable=True)
    resolved_by_rule_id = Column(Integer,  ForeignKey("mapping_rules.id"), nullable=True)
    resolved_at         = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, nullable=False)
    last_processed_at   = Column(DateTime, nullable=True)

class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    id            = Column(Integer,   primary_key=True)
    source        = Column(String(100), nullable=False, index=True)
    location_id   = Column(Integer,   ForeignKey("locations.id"), nullable=True)
    started_at    = Column(DateTime,  nullable=False)
    completed_at  = Column(DateTime,  nullable=True)
    total_in_feed = Column(Integer,   nullable=True)
    new_vehicles     = Column(Integer, default=0, nullable=False)
    updated_vehicles = Column(Integer, default=0, nullable=False)
    removed_vehicles = Column(Integer, default=0, nullable=False)
    success       = Column(Boolean,   nullable=False, default=False)
    error_message = Column(String(1000), nullable=True)
```

---

## Phase Roadmap

### Phase 0 — Database Foundation
**Sub-plan:** `2026-05-17-phase-0-database-foundation.md`
**Produces:** A running Postgres instance with both schemas, Alembic migration tooling, and the canonical junkyard schema applied.

**Scope:**
- Provision a dedicated Postgres container in `scrape_stack` (or extend existing)
- Create schema `junkyard_inventory` and `parts_interchange` in one cluster
- Write the Alembic migration for `junkyard_inventory` schema using the canonical Vehicle schema above (no VehicleDetail)
- Migrate parts-interchange data from whatever current state into the `parts_interchange` schema (parts-loader-v2 handles this)
- Verify both schemas are queryable

**Dependencies:** None — this is the foundation everything else builds on.

---

### Phase 1 — Junkyard Scraper Standardization
**Sub-plan:** `2026-05-17-phase-1-junkyard-scrapers.md`
**Produces:** All 5 scrapers writing to Postgres `junkyard_inventory` schema via the common model. Each scraper has a Docker image, Helm chart, and CI pipeline.

**Scope:**
- Update `common/models.py` to the finalized schema (flattened Vehicle, no VehicleDetail, extras JSON)
- Update `common/db.py` to target Postgres (connection string from env, not SQLite path)
- Migrate each scraper to use common models: `pull_a_part_scraper`, `us_auto_parts_sterling_heights`, `ryans_pic_a_part`, `parts-galore`, `pic-n-pull`
  - For each: replace local models.py with import from common, adapt field mapping in scraper.py
  - Extras JSON: any yard-specific fields that don't map to canonical columns go into `extras`
- Dockerfile per scraper (base image with common + scraper-specific deps)
- Helm chart per scraper (CronJob, ConfigMap, Secret for DB URL)
- GitHub Actions CI: build + push to DockerHub on merge to main

**Dependencies:** Phase 0 (Postgres + schema)

**Scraper inventory:**
| Scraper | Currently uses common schema? | Notes |
|---|---|---|
| `pull_a_part_scraper` | No — has own models.py | Has VehicleDetail detail fetch; move those fields to Vehicle.extras or flat columns |
| `us_auto_parts_sterling_heights` | No — has own models.py | |
| `ryans_pic_a_part` | No — has own models.py | |
| `parts-galore` | No — has own models.py | |
| `pic-n-pull` | Partially — uses common but may need updates for schema changes | |

---

### Phase 2 — Parts-Direct Scraper Modernization
**Sub-plan:** `2026-05-17-phase-2-parts-direct-scraper.md`
**Produces:** parts-direct scraper writes pages/images to webcache/imgcache and structured data to `parts_interchange` schema in Postgres in a single run. Re-runnable on a schedule.

**Scope:**
- Replace `BrowserCache` / `BucketUtils` with `cache_client` from `scrape_stack/libs/cache_client`
- Route all HTTP fetches through `webcache` service; all image fetches through `imgcache` service
- Wire `request_authorization` service for rate limiting
- At scrape time: write structured part/car data directly to Postgres `parts_interchange` schema (upsert, not full reload)
- Preserve existing data structure (the `part`, `car`, `car_parts`, etc. tables are the source of truth — do not alter their shape)
- Add a `scrape_run` audit table to `parts_interchange` schema (analogous to junkyard's `scrape_runs`)
- Dockerfile + Helm CronJob + CI pipeline (same pattern as Phase 1)

**Dependencies:** Phase 0 (Postgres), Phase 1 (cache_client pattern established)

---

### Phase 2b — Tarball Ingestion Script
**Sub-plan:** `2026-05-17-phase-2b-tarball-ingestion.md`
**Produces:** A one-shot script that ingests the existing ~1TB tarball dataset into webcache/imgcache so the cache reflects what was previously scraped.

**Scope:**
- Walk the tarball directory structure (one tarball per manufacturer)
- Extract HTML pages and register them in webcache with canonical URLs (matching the URL pattern the updated scraper would use)
- Extract images and register them in imgcache
- Idempotent — safe to re-run, skips already-cached entries
- This does NOT re-load structured data into Postgres (parts-loader-v2 already handles that)

**Dependencies:** Phase 0, webcache/imgcache services running

---

### Phase 3 — Vehicle-to-Car Mapping Pipeline
**Sub-plan:** `2026-05-17-phase-3-mapping-pipeline.md`
**Produces:** A pipeline that runs after each scrape cycle and attempts to resolve every junkyard vehicle to a `parts_interchange.car.id`.

**Pipeline steps (per vehicle, in order):**
1. VIN decode via NHTSA API (`https://vpic.nhtsa.dot.gov/api/`) → if resolves to car.id, commit `car_id`, confidence=1.0, method="vin_decode"
2. Apply active `MappingRule`s in priority order (location > source > global)
3. Fuzzy match transformed strings against `parts_interchange.make`/`model` tables (threshold ≥ 0.85 → commit)
4. Below threshold → create/update `MappingDiscrepancy`, status="unresolved"
5. No candidate → `MappingDiscrepancy`, status="no_match_in_dataset"

**Scope:**
- Alembic migration: add `car_id`/`car_id_resolved`/`car_id_method`/`car_id_confidence` to `vehicles`; create `mapping_rules` and `mapping_discrepancies` tables
- `vin_decoder.py` — thin async wrapper around NHTSA API, caches results in Postgres (avoid re-fetching same VIN)
- `ymmt_matcher.py` — fuzzy match using `rapidfuzz` against parts_interchange make/model tables
- `rule_engine.py` — apply MappingRules (exact/prefix/regex) with scope resolution
- `resolution_pipeline.py` — orchestrates the above, processes unresolved vehicles in batches
- `reprocess_job.py` — triggered when new rules are approved; re-runs pipeline on unresolved+rule_applied discrepancies
- Manual override: `POST /admin/vehicles/{id}/car-id` sets car_id directly, records method="manual"

**Dependencies:** Phase 0, Phase 1 (vehicles populated in Postgres)

---

### Phase 4 — Inventory Search API
**Sub-plan:** `2026-05-17-phase-4-inventory-search-api.md`
**Produces:** A standalone FastAPI service (or addition to the main API) exposing `GET /inventory/search`.

**Endpoint:**
```
GET /inventory/search?car_ids=1,2,3&zip=48093&radius_miles=50
```

**Response:** Locations sorted by distance_miles, each with matching vehicle list.

**Scope:**
- `uszipcode` package for offline zip→lat/lng (no external API)
- Haversine distance query in SQL (see handoff doc for the exact SQL)
- Only returns `is_active=true` vehicles at `is_active=true` locations
- Returns `matching_vehicles` array per location with year/make/model/row/car_id

**Dependencies:** Phase 0, Phase 1, Phase 3 (vehicles need car_id populated)

---

### Phase 5 — Admin Panel (Discrepancy Review + Rule Management)
**Sub-plan:** `2026-05-17-phase-5-admin-panel.md`
**Produces:** A web UI for reviewing mapping discrepancies, creating correction rules, and approving LLM suggestions.

**Scope:**
- Grouped discrepancy view: group by `(source, raw_make, raw_model)` with count — not 1 row per vehicle
- Filter modes: unresolved / pending LLM rule / no_match_in_dataset / ignored
- Rule creation form: pre-filled from selected discrepancy, scope selector, saves rule + triggers re-process
- Manual override: direct car_id assignment from discrepancy row
- LLM rule suggester: batch job sends grouped unresolved strings to local inference, returns MappingRule suggestions with rationale
- LLM suggestion approval queue: scan/approve flow, approved rules trigger re-process

**Dependencies:** Phase 3 (mapping pipeline + tables)

---

### Phase 6 — API v2 + UI v2 (Fresh Implementations)
**Sub-plan:** `2026-05-17-phase-6-api-ui-v2.md`
**Produces:** Production-ready FastAPI backend and React/Vite frontend replacing the POC api-v2 and ui-v2.

**Requirements (to be detailed when writing sub-plan):**
- Parts search: vehicle picker → interchange lookup → compatible car list
- Junkyard search: takes compatible car IDs + user zip → calls inventory search API → ranked yard list with match counts
- Vehicle garage (user's saved vehicles)
- Part detail with diagram + images
- Admin panel integration (or separate route)
- Auth: API keys for admin; no auth for public search

**Note:** api-v2 and ui-v2 directories in `parts_interchange/` are POCs and should not be carried forward. The v2 implementations start fresh in new directories (`api-v3/` and `ui-v3/` to avoid confusion, or rename as you prefer).

**Dependencies:** Phase 4 (inventory search API), Phase 5 (admin panel requirements clarified)

---

## Dependency Graph

```
Phase 0 (DB Foundation)
    ↓
Phase 1 (Junkyard Scrapers) ──── Phase 2 (parts-direct Scraper)
    ↓                                    ↓
Phase 3 (Mapping Pipeline)        Phase 2b (Tarball Ingestion)
    ↓
Phase 4 (Inventory Search API)
    ↓
Phase 5 (Admin Panel)
    ↓
Phase 6 (API v2 + UI v2)
```

Phases 1 and 2 can run in parallel after Phase 0. Phase 2b can run any time after Phase 0 (it's independent of Phase 1). Phases 3–6 are sequential.

---

## Progress Tracker

| Phase | Sub-plan | Status |
|---|---|---|
| 0 — DB Foundation | `phase-0-database-foundation.md` | Not started |
| 1 — Junkyard Scrapers | `phase-1-junkyard-scrapers.md` | Not started |
| 2 — parts-direct Modernization | `phase-2-parts-direct-scraper.md` | Not started |
| 2b — Tarball Ingestion | `phase-2b-tarball-ingestion.md` | Not started |
| 3 — Mapping Pipeline | `phase-3-mapping-pipeline.md` | Not started |
| 4 — Inventory Search API | `phase-4-inventory-search-api.md` | Not started |
| 5 — Admin Panel | `phase-5-admin-panel.md` | Not started |
| 6 — API v2 + UI v2 | `phase-6-api-ui-v2.md` | Not started |

---

## Reference: Key File Locations

| System | Location |
|---|---|
| Common junkyard schema | `web_scrapers/junkyard_inventory_scrapers/common/models.py` |
| Pull-A-Part scraper | `web_scrapers/junkyard_inventory_scrapers/pull_a_part_scraper/` |
| US Auto scraper | `web_scrapers/junkyard_inventory_scrapers/us_auto_parts_sterling_heights/` |
| Ryan's scraper | `web_scrapers/junkyard_inventory_scrapers/ryans_pic_a_part/` |
| Parts-Galore scraper | `web_scrapers/junkyard_inventory_scrapers/parts-galore/` |
| Pic-N-Pull scraper | `web_scrapers/junkyard_inventory_scrapers/pic-n-pull/` |
| parts-direct scraper | `web_scrapers/parts_direct/singlethreaded-scraper/` |
| scrape_stack services | `web_scrapers/scrape_stack/services/` (webcache, imgcache, request_authorization) |
| cache_client library | `web_scrapers/scrape_stack/libs/cache_client/` |
| parts-loader-v2 | `parts_interchange/parts-loader-v2/` |
| parts_interchange models | `parts_interchange/api/src/models.py` |
| Handoff document | `parts_interchange/docs/inventory-integration/handoff.md` |
