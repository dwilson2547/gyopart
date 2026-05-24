# gyopart Docs — Obsidian Canvas Diagrams Design

**Date:** 2026-05-20
**Status:** Approved

## Overview

Add a `docs/` folder to the gyopart monorepo containing six Obsidian Canvas (`.canvas`) files that document the system architecture, data model, and key operational flows. The canvases are medium-detail: components + key data passed between them, decision points, and important tables — enough to reason about the system without reading code.

## File Structure

```
docs/
  architecture/
    system-architecture.canvas   ← hub; contains file-link nodes to all flow canvases
    data-model.canvas
  flows/
    vin-mapping-pipeline.canvas
    user-search-flow.canvas
    scraper-ingestion.canvas
    admin-discrepancy-resolution.canvas
```

`architecture/` holds static structure diagrams (what the system is). `flows/` holds dynamic process diagrams (what the system does). `system-architecture.canvas` is the entry point and links to all others via Obsidian file-link nodes.

## Node Color Conventions

Consistent across all six canvases. Obsidian Canvas color values 1–6:

| Color | Obsidian value | Used for |
|-------|---------------|----------|
| Cyan/blue | 5 | Services & APIs (gyopart-ui, gyopart-api, inventory_api, admin_api) |
| Green | 4 | Databases & storage (junkyard_inventory schema, parts_interchange schema, VinCache, SQLite scraper DBs) |
| Orange | 2 | External systems (NHTSA vpic API, junkyard websites, PyPI, Claude API) |
| Yellow | 3 | Decision / branch points (VIN valid? Cache hit? Match found ≥0.85? Confidence ≥0.80?) |
| Purple | 6 | Human actors (gyopart.com user, admin reviewer) |
| Red | 1 | Error / failure states (MappingDiscrepancy created, unresolved, NHTSA error, 502) |

Edges carry short labels for key data in transit (e.g., `car_ids + zip + radius`, `VIN decode result`). Group boxes are used to visually cluster related components (e.g., junkyard-platform package, junkyard_inventory schema).

## Per-Canvas Content Plan

### `architecture/system-architecture.canvas` (hub)

**Nodes:** gyopart-ui (port 5173), gyopart-api (port 8200), inventory_api, admin_api, pipeline CLI, junkyard scrapers, parts_interchange DB, junkyard_inventory DB, NHTSA API, Claude API.

**Edges:** Key data labels — `cascading picker requests`, `car_ids + zip + radius`, `VIN decode`, `inventory results`, `MappingRule suggestions`.

**File links:** One file-link node for each of the four flow canvases and for `data-model.canvas`, positioned in a dedicated "Diagrams" group at the bottom of the canvas.

**Groups:** `junkyard-platform` package boundary, `junkyard_inventory schema`, `parts_interchange schema`.

---

### `architecture/data-model.canvas`

Two top-level group boxes, one per schema.

**junkyard_inventory schema:** Location, Vehicle (36-col flat schema, extras JSONB, VIN as dedup key, car_id/car_id_resolved/car_id_method/car_id_confidence), MappingRule, MappingDiscrepancy, ScrapeRun, VinCache. Key FK edges: Vehicle → Location, MappingDiscrepancy → Vehicle.

**parts_interchange schema:** Year, Make, Model, Car (Year + Make + Model), Part, CarParts (Car ↔ Part junction). Key FK edges: Car → Year/Make/Model, CarParts → Car + Part.

Cross-schema edge: Vehicle.car_id → Car.id (the mapping target).

---

### `flows/vin-mapping-pipeline.canvas`

Entry: **Unresolved Vehicle** (car_id_resolved = false).

Steps:
1. VIN present & 17 chars? → no → skip to rule engine
2. VinCache hit? → yes → use cached result; no → NHTSA vpic API (1s rate limit)
3. NHTSA returns make + model + year? → no → mark error in VinCache, skip to rule engine
4. Exact match in parts_interchange (year/make/model)? → yes → write car_id, method=vin_decode, confidence=1.0 → **Resolved**
5. Rule engine: apply active MappingRules (ordered by scope + priority) to transform make/model/trim
6. Fuzzy YMMT match against parts_interchange (threshold ≥ 0.85) → match? → write car_id, method=ymmt_match or rule_applied, confidence=score → **Resolved**
7. No match → **MappingDiscrepancy** created (status=unresolved) → **Unresolved**

---

### `flows/user-search-flow.canvas`

Entry: **User on gyopart.com**.

Steps:
1. Cascading vehicle picker: Year → Make → Model → Trim → Engine (gyopart-api `/v1/vehicles/*`)
2. Parts list for selected car (gyopart-api `/v1/parts?car_id=…`)
3. User selects a part + enters zip code
4. gyopart-api `/v1/search` resolves compatible `car_ids` from parts_interchange `car_parts`
5. Calls inventory_api `GET /inventory/search?car_ids=…&zip=…&radius_miles=…`
6. inventory_api: offline zip → lat/lng (uszipcode), haversine distance filter, query junkyard_inventory for matching vehicles
7. Returns locations sorted by distance with vehicle match counts
8. gyopart-ui renders ranked junkyard list

---

### `flows/scraper-ingestion.canvas`

Entry: **Scraper run triggered** (CLI or scheduled).

Steps:
1. Fetch vehicle list from junkyard site (platform varies: WordPress/WP Car Manager, custom REST API, HTMX, static HTML — see scraper notes for platform details)
2. Parse vehicle record: year, make, model, trim, VIN, row/section, location
3. Lookup or create Location in junkyard_inventory
4. Dedup: VIN already in Vehicle table for this location? → skip
5. Insert Vehicle row via junkyard_common models
6. Update ScrapeRun record (vehicle count, timestamp)
7. New vehicles enter pipeline queue (car_id_resolved = false)

---

### `flows/admin-discrepancy-resolution.canvas`

Entry: **MappingDiscrepancy** (status=unresolved).

Steps:
1. Admin opens `/admin/ui/discrepancies` (admin_api, auth: X-Admin-Key header)
2. LLM suggester: Claude API generates MappingRule suggestion (model from ANTHROPIC_MODEL env, MIN_CONFIDENCE=0.80) → inserts rule with `is_active=False, created_by=llm_suggested`
3. Confidence ≥ 0.80? → rule shown in `/admin/ui/llm-queue`; below threshold → shown for manual review
4. Admin approves → rule `is_active=True` → **reprocess_job** re-runs pipeline on affected vehicles
5. Admin rejects → rule deleted
6. Manual override path: admin assigns `car_id` directly → Vehicle.car_id set, MappingDiscrepancy.status=manual → **Resolved**

---

## Canvas Format Notes

All files use the Obsidian Canvas JSON schema:
- `nodes` array: each node has `id`, `type` (`text` or `file`), `x`, `y`, `width`, `height`, `color` (1–6 string), and `text` (markdown) or `file` (vault-relative path)
- `edges` array: each edge has `id`, `fromNode`, `toNode`, `label` (optional), `fromSide`, `toSide`
- File-link nodes in system-architecture.canvas use `"type": "file"` with a vault-root-relative path. If `docs/` is opened as the Obsidian vault root, paths are `flows/vin-mapping-pipeline.canvas` etc. If the monorepo root is the vault, paths become `docs/flows/vin-mapping-pipeline.canvas` etc. The canvas files will be generated assuming `docs/` is the vault root — the simpler path.

Nodes are sized to fit their label. Decision nodes (yellow) use a taller aspect ratio to suggest a diamond shape. Group boxes use Obsidian's native group type.

## Out of Scope

- Deployment / infrastructure diagrams (no Docker, CI/CD, or cloud topology)
- scrape_stack repo internals (separate universal repo, not part of gyopart)
- parts-interchange legacy loader internals (parts-loader-v2 is one-time ingestion only)
- API route-level detail (function names, exact SQL queries)
