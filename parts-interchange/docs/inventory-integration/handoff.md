# Junkyard Inventory Scraper — Claude Code Handoff Document

## Project Overview

This project consists of two systems that need to be connected:

1. **workspace/parts_interchange** — An existing Flask application with a scraped catalog of OEM parts and vehicle applications going back to 1984. The core interchange query is already working: given a car, find all other cars that share parts via the `car_parts` junction table. Source data was scraped from a major parts catalog site over approximately 4 years.

2. **workspace/web_scrapers/junkyard _inventory_scrapers** — A newer system of per-yard scrapers running on cron schedules, writing into a shared SQLAlchemy schema. Currently ~5 yards are tested locally. The goal is to expand coverage, link yard inventory back to the parts-interchange `Car` table, and expose a location-aware search to the parts-interchange frontend.

The combined user workflow is:

> User selects their vehicle + part on parts-interchange → system finds all compatible cars → queries junkyard inventory for those car IDs → returns yards sorted by distance with match counts

---

## Existing Schemas

### Scraper Schema (`models.py` — SQLAlchemy Core)

**`locations`** — One row per physical yard location.
- `source` + `source_location_id` form a unique key (e.g. `"pull_a_part"` + `"42"`)
- `chain` — parent company name if part of a chain (e.g. `"Pull-A-Part"`)
- `lat` / `lng` — for distance queries
- `is_active`, `first_seen_at`, `last_seen_at` — lifecycle tracking

**`vehicles`** — One row per vehicle across all yards.
- `source` + `source_key` form a unique key; source_key format varies by scraper (e.g. PAP uses `"<ticket_id>:<line_id>"`, US Auto uses stock number)
- `source` is intentionally denormalized from `location` for query convenience
- `vin` indexed — available from most yards, primary deduplication key
- `is_active`, `first_seen_at`, `last_seen_at` — inventory freshness tracking
- **Needs addition:** `car_id`, `car_id_resolved`, `car_id_method`, `car_id_confidence` (see Linking section)

**`vehicle_details`** — 1:1 extended attributes, populated by a separate async enrichment pass for some yards.
- Covers trim, body type, drivetrain, engine spec, transmission
- `engine_cylinders`, `engine_size`, `trans_type` important for accurate part fitment
- **Needs addition:** `extra JSON` column for yard-specific fields that don't fit the fixed schema

**`scrape_runs`** — Audit log per scraper execution.
- Tracks `new_vehicles`, `updated_vehicles`, `removed_vehicles`, `success`, `error_message`

### Parts-Interchange Schema (`models.py` — Flask-SQLAlchemy)

**`car`** — Normalized vehicle records via FK to `year`, `make`, `model`, `trim`, `engine` tables. Coverage: 1984–present (scraped ~4 years ago, not yet continuously updated).

**`car_parts`** — Junction table linking cars to parts. This IS the interchange table — the query "find all cars that use this part" runs here.

**`part`** — OEM part records with `part_number`, `manufacturer_id`, `category_id`. The `applications` text column is a non-normalized legacy field from the source and should be ignored; `car_parts` is the source of truth.

**`manufacturer`** — Parts manufacturer (e.g. Dorman, Bosch, ACDelco).

**`category` / `subcategory`** — Part taxonomy.

**`diagram` / `diagram_parts`** — Exploded-view diagrams with part position indices.

**`image` / `part_images`** — Images persisted to bucket storage; `saved` and `uploaded` flags track pipeline state.

---

## Data Facts & Constraints

- Parts dataset covers **1984–present**. Vehicles from the 1960s–70s are regularly seen in yards and **cannot be matched** — this is expected, not an error.
- Compressed parts dataset is **~1TB**, mostly images. Bulk ingestion must use CSV + direct DB load; ORM-based ingestion takes days and is not viable.
- Raw HTML pages and API responses are cached in a local directory. Cache never expires — stores new versions on re-fetch. All scrapers route through this cache, so re-parsing without re-fetching is possible.
- VIN is available from most yards and should be the primary vehicle identity/deduplication key.
- Part data schema is considered stable (no immediate changes in sight). Junkyard inventory is the active data pipeline.

---

## Completed Work / What's Working

- 5 junkyard scrapers each persisting to its own format, one is using the common format.
- Per-yard scrapers handle their own location seeding (single-location) or dynamic location discovery (multi-location chains like Pull-A-Part)
- Webcache service caching all HTTP pages for scrapers
- Request auth handling rate limiting
- Parts-interchange frontend with working interchange query (get compatible cars for a given car+part)
- Full parts catalog persisted including images, diagrams, part-to-car mappings

---

## New Columns Required on `vehicles`

Add to the `Vehicle` model and generate a migration:

```python
car_id            = Column(Integer,  nullable=True, index=True)  # FK to parts-interchange car.id
car_id_resolved   = Column(Boolean,  nullable=False, default=False)
car_id_method     = Column(String(20), nullable=True)  # "vin_decode" | "ymmt_match" | "manual" | "rule_applied"
car_id_confidence = Column(Float,    nullable=True)    # 1.0 = VIN decode, <1.0 = fuzzy/rule
```

---

## New Columns Required on `vehicle_details`

Add overflow column for yard-specific fields:

```python
extra = Column(JSON, nullable=True)  # arbitrary yard-specific fields that don't fit fixed schema
```

---

## New Tables Required (Scraper DB)

### `mapping_rules`

Entity resolution rules created by admin or LLM, applied before fuzzy matching.

```python
class MappingRule(Base):
    __tablename__ = "mapping_rules"

    id          = Column(Integer, primary_key=True)

    # Scope hierarchy: location overrides source overrides global
    scope       = Column(String(20), nullable=False)   # "global" | "source" | "location"
    source      = Column(String(100), nullable=True)   # matches Vehicle.source
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Rule definition
    field           = Column(String(50),  nullable=False)   # "make" | "model" | "trim"
    rule_type       = Column(String(20),  nullable=False)   # "exact" | "prefix" | "regex"
    raw_value       = Column(String(200), nullable=False)   # input pattern
    canonical_value = Column(String(200), nullable=False)   # output (pre-FK-lookup canonical string)
    make_context    = Column(String(100), nullable=True)    # constrain model/trim rules to a specific make

    priority      = Column(Integer, default=100)   # lower = evaluated first; location rules should default lower
    is_active     = Column(Boolean, default=True)
    created_by    = Column(String(20), nullable=False)   # "manual" | "llm_suggested" | "import"
    created_at    = Column(DateTime, nullable=False)
    applied_count = Column(Integer,  default=0)

    # LLM rule review workflow
    llm_confidence = Column(Float,        nullable=True)
    llm_rationale  = Column(String(1000), nullable=True)
    approved_at    = Column(DateTime,     nullable=True)
    approved_by    = Column(String(100),  nullable=True)
```

### `mapping_discrepancies`

Vehicles that failed to resolve cleanly to a `car_id`.

```python
class MappingDiscrepancy(Base):
    __tablename__ = "mapping_discrepancies"

    id         = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), unique=True, nullable=False)

    # Raw strings exactly as received from the yard
    raw_year  = Column(String(20),  nullable=True)
    raw_make  = Column(String(100), nullable=True)
    raw_model = Column(String(200), nullable=True)
    raw_trim  = Column(String(200), nullable=True)

    # Best fuzzy attempt (pre-rule or post-rule)
    fuzzy_make_match  = Column(String(100), nullable=True)
    fuzzy_make_score  = Column(Float,       nullable=True)
    fuzzy_model_match = Column(String(200), nullable=True)
    fuzzy_model_score = Column(Float,       nullable=True)
    candidate_car_id  = Column(Integer,     nullable=True)  # best guess, not committed

    # Status — IMPORTANT: distinguish resolution failure from coverage gap
    status = Column(String(30), nullable=False, default="unresolved")
    # Values:
    #   "unresolved"          — fuzzy match below threshold; a rule may fix this
    #   "pending_rule"        — LLM has suggested a rule, awaiting approval
    #   "rule_applied"        — resolved by a mapping rule
    #   "manual"              — resolved by admin direct assignment
    #   "ignored"             — admin marked as intentionally unresolvable
    #   "no_match_in_dataset" — strings parsed fine but no Car in parts-interchange matches
    #                           (pre-1984, obscure trim, coverage gap — rules won't help)

    resolved_car_id     = Column(Integer,  nullable=True)
    resolved_by_rule_id = Column(Integer,  ForeignKey("mapping_rules.id"), nullable=True)
    resolved_at         = Column(DateTime, nullable=True)

    created_at        = Column(DateTime, nullable=False)
    last_processed_at = Column(DateTime, nullable=True)
```

---

## Vehicle Resolution Pipeline

Runs after each scrape cycle upsert. Process each unresolved vehicle in order:

```
1. VIN decode (NHTSA free API: https://vpic.nhtsa.dot.gov/api/)
      → If full YMMT resolves to a Car.id → commit car_id, confidence=1.0, method="vin_decode", done

2. Apply active MappingRules in priority order (lower priority value = evaluated first)
      → Scope resolution: location-specific rules first, then source-level, then global
      → Rules transform raw strings before fuzzy matching

3. Fuzzy match transformed strings against parts-interchange Make/Model tables
      → Use make_context to constrain model rule application (e.g. "GT" means different things for Ford vs Pontiac)
      → Score >= 0.85 → commit car_id, confidence=score, method="ymmt_match" or "rule_applied"

4. Score < 0.85 but candidate exists
      → Create/update MappingDiscrepancy, status="unresolved", store candidate_car_id and scores

5. No candidate at all
      → MappingDiscrepancy, status="no_match_in_dataset"
      → Covers pre-1984 vehicles and genuine coverage gaps — not fixable with rules
```

**Re-processing trigger:** Admin creates rules → triggers re-process job on all `unresolved` and `rule_applied` discrepancies → vehicles that now resolve get `car_id` committed, `applied_count` incremented on the rule.

---

## Inventory Search API

A small API endpoint on the scraper service, called by parts-interchange after resolving compatible car IDs.

```
GET /inventory/search?car_ids=1,2,3,47&zip=48093&radius_miles=50
```

**Response shape:**
```json
[
  {
    "location_id": 12,
    "name": "Pull-A-Part — Warren",
    "address": "1234 Van Dyke Ave",
    "city": "Warren",
    "state": "MI",
    "lat": 42.49,
    "lng": -83.01,
    "distance_miles": 4.2,
    "matching_vehicle_count": 17,
    "matching_vehicles": [
      { "vehicle_id": 884, "year": 2003, "make": "Ford", "model": "Mustang", "row": "B14", "car_id": 47 }
    ]
  }
]
```

Sorted by `distance_miles` ascending. Frontend can highlight that a yard 10 miles out has 40 matches vs 3 at the nearest yard.

**Zip → coordinates:** Use the `uszipcode` Python package (offline, no API dependency, ~50ms lookup). Seed from Census ZCTA data if you prefer zero third-party packages.

**Core SQL:**
```sql
SELECT
    l.id, l.name, l.address, l.city, l.state, l.lat, l.lng,
    COUNT(v.id) AS matching_vehicle_count,
    (3959 * acos(
        cos(radians(:user_lat)) * cos(radians(l.lat)) *
        cos(radians(l.lng) - radians(:user_lng)) +
        sin(radians(:user_lat)) * sin(radians(l.lat))
    )) AS distance_miles
FROM locations l
JOIN vehicles v ON v.location_id = l.id
WHERE
    v.car_id IN :compatible_car_ids
    AND v.is_active = true
    AND l.is_active = true
GROUP BY l.id
HAVING distance_miles < :radius_miles
ORDER BY distance_miles ASC
```

---

## Admin Panel — Discrepancy Review

### Primary view

Group discrepancies by `(source, raw_make, raw_model)` with vehicle count — so 847 rows of "us_auto / mtg / mustang" appear as one actionable row, not 847. Surface `candidate_car_id` as a suggested resolution so manual approval is a single click.

### Filter modes

- **Unresolved** — needs a rule or manual resolution
- **Pending LLM rule** — LLM suggested a rule, awaiting human approval
- **No match in dataset** — pre-1984 or genuine coverage gap; rules won't help; displayed separately so they don't pollute the actionable queue
- **Ignored** — admin-dismissed; hidden by default

### Rule creation UX

Admin sees a discrepancy group, can create a rule directly from that row:
- Pre-fills `field`, `raw_value` from the discrepancy
- `scope` defaults to `source`-level, can be narrowed to location or widened to global
- `canonical_value` pre-filled from `candidate_car_id` lookup if available
- On save → triggers re-process of all discrepancies matching that rule

### LLM rule suggestion workflow

- Batch unresolved discrepancies grouped by source
- Send raw strings + canonical Make/Model lists to local inference
- LLM returns suggested rules (not direct resolutions) — rules are auditable and reusable
- Rules land with `created_by="llm_suggested"`, `approved_at=NULL`
- Admin sees separate "LLM Suggestions" queue — review is a scan/approve flow
- `llm_rationale` column stores the model's explanation for each suggestion

---

## Known Scope Boundaries & Decisions

| Decision | Rationale |
|---|---|
| VIN is primary deduplication key | Available from most yards; NHTSA decode is free and reliable post-1980 |
| pre-1984 vehicles → `no_match_in_dataset`, not an error | Parts-interchange coverage starts at 1984 by design |
| `applications` column on `Part` is ignored | `car_parts` junction table is the source of truth for interchange |
| ORM ingestion not used for bulk parts data | Takes days; CSV bulk load required |
| LLM creates rule suggestions, not direct resolutions | Rules are auditable, reusable, and correctable; direct resolutions are not |
| LLM rules require human approval before activation | Maintains data quality during model warm-up period |
| Webcache never expires, stores versions | Enables re-parse without re-fetch; cache key should be stable canonical URL |
| `source` denormalized on `Vehicle` | Avoids join on every query; cost is negligible |

---

## Immediate Next Steps (Suggested Order)

1. **Schema migrations** — add `car_id` columns to `vehicles`, `extra` JSON to `vehicle_details`, create `mapping_rules` and `mapping_discrepancies` tables
2. **NHTSA VIN decode service** — thin wrapper around the NHTSA API, cache results locally
3. **Fuzzy YMMT matcher** — match raw make/model strings against parts-interchange `make`/`model` tables, return score + candidate `car_id`
4. **Resolution pipeline** — orchestrate VIN decode → rule application → fuzzy match → discrepancy creation
5. **Inventory search API endpoint** — `/inventory/search` with haversine query, zip decode via `uszipcode`
6. **Admin discrepancy panel** — grouped view, rule creation form, re-process trigger
7. **LLM rule suggester** — batch job against local inference, suggestion queue in admin panel
8. **Expand scraper coverage** — additional yards (Car-Part.com portals, Pull-A-Part locations, LKQ, Pick-n-Pull, Pull-A-Part, U-Pull-&-Pay, Fenix Parts)
9. **Parts-interchange frontend integration** — call inventory search API after compatible car resolution, display yard map/list

---

## Scraper Expansion Targets

Yards and aggregators worth implementing next, in rough priority order:

- **Car-Part.com** — Aggregates thousands of independent yards; Hollander-powered search; consider contacting for PartLink API access before scraping
- **LKQ Online** (`lkqonline.com`) — Large chain, proper inventory search
- **Pick-n-Pull** (`picknpull.com`, LKQ subsidiary) — Location-based inventory
- **U-Pull-&-Pay** (`upullandpay.com`)
- **Fenix Parts** (`fenixparts.com`) — Consolidates several regional yards
- **Car-Part Pro portals** — Many independents share the same template; one scraper covers many
- **Row52** — Pick-your-part focused, cleaner HTML than most

Check ToS before scraping each. Be conservative with request rates — many yards run underpowered shared hosting.

---

## Reference: Hollander Numbers

If expanding into interchange data beyond the `car_parts` junction table, Hollander interchange numbers are the industry standard. Most yard inventory systems encode parts by Hollander number. Not currently used in this project but relevant if you later want to match yard-listed parts (not just vehicles) to your parts catalog.