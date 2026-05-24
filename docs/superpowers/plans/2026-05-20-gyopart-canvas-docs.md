# gyopart Canvas Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create six Obsidian Canvas (`.canvas`) files documenting the gyopart system — architecture, data model, and four operational flows.

**Architecture:** Pure JSON files, no build step. Six canvases split into `docs/architecture/` (static structure) and `docs/flows/` (dynamic processes). `system-architecture.canvas` is built last and acts as the hub, embedding file-link nodes pointing to the other five canvases. All canvases share a color convention: services=cyan(`"5"`), databases=green(`"4"`), external=orange(`"2"`), decisions=yellow(`"3"`), humans=purple(`"6"`), errors=red(`"1"`). File-link paths assume `docs/` is opened as the Obsidian vault root.

**Tech Stack:** Obsidian Canvas JSON (nodes + edges arrays). Validate with `python -m json.tool`. No dependencies.

---

## File Map

| File | Type | Purpose |
|------|------|---------|
| `docs/architecture/data-model.canvas` | Create | ER diagram for both Postgres schemas |
| `docs/architecture/system-architecture.canvas` | Create | Hub — full system map + links to all flows |
| `docs/flows/vin-mapping-pipeline.canvas` | Create | VIN decode → rule engine → YMMT → discrepancy |
| `docs/flows/user-search-flow.canvas` | Create | User picks car + part → ranked junkyard results |
| `docs/flows/scraper-ingestion.canvas` | Create | Scraper fetch → parse → dedup → DB insert |
| `docs/flows/admin-discrepancy-resolution.canvas` | Create | Unresolved → LLM suggest → approve → reprocess |

---

## Task 1: Create directory structure

**Files:**
- Create: `docs/architecture/` (directory)
- Create: `docs/flows/` (directory)

- [ ] **Step 1: Create directories**

```bash
mkdir -p docs/architecture docs/flows
```

Expected: no output, exit code 0.

- [ ] **Step 2: Verify**

```bash
ls docs/
```

Expected output:
```
architecture  flows  superpowers
```

---

## Task 2: data-model.canvas

**Files:**
- Create: `docs/architecture/data-model.canvas`

Two group boxes (one per Postgres schema) with table nodes inside. A cross-schema edge shows the resolved mapping from `Vehicle.car_id` → `Car.id`.

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "grp_ji",
      "type": "group",
      "label": "junkyard_inventory schema (Postgres)",
      "x": -1050,
      "y": -600,
      "width": 800,
      "height": 1000
    },
    {
      "id": "n_loc",
      "type": "text",
      "text": "## Location\n**id**, name\naddress, city, state, zip\nlat, lng, phone, url\nsource *(scraper name)*",
      "x": -1020,
      "y": -560,
      "width": 320,
      "height": 160,
      "color": "4"
    },
    {
      "id": "n_veh",
      "type": "text",
      "text": "## Vehicle\n**id**, vin *(dedup key, 17 chars)*\nyear, make, model, trim\nextras *(JSONB — yard-specific fields)*\ncar_id, car_id_resolved\ncar_id_method, car_id_confidence\nlocation_id → Location",
      "x": -1020,
      "y": -360,
      "width": 320,
      "height": 220,
      "color": "4"
    },
    {
      "id": "n_srun",
      "type": "text",
      "text": "## ScrapeRun\n**id**, source\nlocation_id → Location\nstarted_at, finished_at\nvehicle_count, status",
      "x": -1020,
      "y": -100,
      "width": 320,
      "height": 140,
      "color": "4"
    },
    {
      "id": "n_rule",
      "type": "text",
      "text": "## MappingRule\n**id**, scope, priority\nmatch_make, match_model, match_trim\nreplacement_make, replacement_model\nis_active, created_by",
      "x": -680,
      "y": -560,
      "width": 300,
      "height": 160,
      "color": "4"
    },
    {
      "id": "n_disc",
      "type": "text",
      "text": "## MappingDiscrepancy\n**id**, vehicle_id → Vehicle\nraw_year, raw_make, raw_model, raw_trim\nfuzzy_make/model_match, fuzzy_scores\ncandidate_car_id, status\ncreated_at, last_processed_at",
      "x": -680,
      "y": -360,
      "width": 300,
      "height": 220,
      "color": "4"
    },
    {
      "id": "n_vcache",
      "type": "text",
      "text": "## VinCache\n**vin** *(PK, 17 chars)*\nmake, model, model_year, trim\nerror_code, fetched_at",
      "x": -680,
      "y": -100,
      "width": 300,
      "height": 120,
      "color": "4"
    },
    {
      "id": "grp_pi",
      "type": "group",
      "label": "parts_interchange schema (Postgres)",
      "x": -150,
      "y": -600,
      "width": 720,
      "height": 700
    },
    {
      "id": "n_yr",
      "type": "text",
      "text": "## Year\n**id**, name *(e.g. \"2015\")*",
      "x": -120,
      "y": -560,
      "width": 200,
      "height": 80,
      "color": "4"
    },
    {
      "id": "n_mk",
      "type": "text",
      "text": "## Make\n**id**, name",
      "x": 130,
      "y": -560,
      "width": 200,
      "height": 80,
      "color": "4"
    },
    {
      "id": "n_mdl",
      "type": "text",
      "text": "## Model\n**id**, name\nmake_id → Make",
      "x": 130,
      "y": -440,
      "width": 200,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_car",
      "type": "text",
      "text": "## Car\n**id**\nyear_id → Year\nmake_id → Make\nmodel_id → Model",
      "x": -120,
      "y": -300,
      "width": 200,
      "height": 120,
      "color": "4"
    },
    {
      "id": "n_part",
      "type": "text",
      "text": "## Part\n**id**, name, category\ndescription",
      "x": 130,
      "y": -300,
      "width": 200,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_cp",
      "type": "text",
      "text": "## CarParts *(junction)*\ncar_id → Car\npart_id → Part",
      "x": -10,
      "y": -140,
      "width": 220,
      "height": 100,
      "color": "4"
    }
  ],
  "edges": [
    {"id": "e_disc_veh", "fromNode": "n_disc", "toNode": "n_veh", "fromSide": "left", "toSide": "right", "label": "vehicle_id"},
    {"id": "e_veh_loc", "fromNode": "n_veh", "toNode": "n_loc", "fromSide": "top", "toSide": "bottom", "label": "location_id"},
    {"id": "e_veh_vc",  "fromNode": "n_veh", "toNode": "n_vcache", "fromSide": "bottom", "toSide": "top", "label": "vin"},
    {"id": "e_srun_loc","fromNode": "n_srun","toNode": "n_loc", "fromSide": "top", "toSide": "bottom", "label": "location_id"},
    {"id": "e_mdl_mk",  "fromNode": "n_mdl", "toNode": "n_mk", "fromSide": "top", "toSide": "bottom", "label": "make_id"},
    {"id": "e_car_yr",  "fromNode": "n_car", "toNode": "n_yr", "fromSide": "top", "toSide": "bottom", "label": "year_id"},
    {"id": "e_car_mk",  "fromNode": "n_car", "toNode": "n_mk", "fromSide": "right", "toSide": "left", "label": "make_id"},
    {"id": "e_car_mdl", "fromNode": "n_car", "toNode": "n_mdl", "fromSide": "right", "toSide": "bottom", "label": "model_id"},
    {"id": "e_cp_car",  "fromNode": "n_cp",  "toNode": "n_car",  "fromSide": "left",  "toSide": "bottom", "label": "car_id"},
    {"id": "e_cp_part", "fromNode": "n_cp",  "toNode": "n_part", "fromSide": "right", "toSide": "bottom", "label": "part_id"},
    {"id": "e_veh_car", "fromNode": "n_veh", "toNode": "n_car",  "fromSide": "right", "toSide": "left",   "label": "car_id → id\n(resolved mapping)", "color": "6"}
  ]
}
```

- [ ] **Step 2: Validate JSON**

```bash
python -m json.tool docs/architecture/data-model.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/data-model.canvas
git commit -m "docs: add data-model canvas (ER diagram for both schemas)"
```

---

## Task 3: vin-mapping-pipeline.canvas

**Files:**
- Create: `docs/flows/vin-mapping-pipeline.canvas`

Top-to-bottom flow. Decision nodes (yellow) branch left to failures and right to success. VinCache and NHTSA appear as side resources accessed by the Decode VIN step.

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "n_entry",
      "type": "text",
      "text": "## Unresolved Vehicle\n`car_id_resolved = false`\n*(queried from junkyard_inventory)*",
      "x": -160,
      "y": -900,
      "width": 320,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_vin_valid",
      "type": "text",
      "text": "VIN present?\n*(non-null, 17 chars)*",
      "x": -110,
      "y": -760,
      "width": 220,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_decode",
      "type": "text",
      "text": "## Decode VIN\nVinCache lookup first\n→ NHTSA fetch on miss\n*(1s rate limit between calls)*",
      "x": -140,
      "y": -630,
      "width": 280,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_vcache",
      "type": "text",
      "text": "## VinCache\njunkyard_inventory schema\nvin, make, model, model_year\ntrim, error_code, fetched_at",
      "x": 220,
      "y": -720,
      "width": 280,
      "height": 140,
      "color": "4"
    },
    {
      "id": "n_nhtsa",
      "type": "text",
      "text": "## NHTSA vpic API\nvpic.nhtsa.dot.gov\n`/decodevin/{vin}?format=json`",
      "x": 220,
      "y": -540,
      "width": 280,
      "height": 100,
      "color": "2"
    },
    {
      "id": "n_pi_resolve",
      "type": "text",
      "text": "Exact match in parts_interchange?\n*(year + make + model)*",
      "x": -120,
      "y": -460,
      "width": 240,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_resolved_vin",
      "type": "text",
      "text": "## ✓ Resolved\n`car_id_method = vin_decode`\n`car_id_confidence = 1.0`",
      "x": 220,
      "y": -320,
      "width": 280,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_rule_engine",
      "type": "text",
      "text": "## Rule Engine\nApply active MappingRules\nordered by scope + priority\n*(transform make / model / trim)*",
      "x": -140,
      "y": -320,
      "width": 280,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_ymmt",
      "type": "text",
      "text": "Fuzzy YMMT match ≥ 0.85?\n*(against parts_interchange cars)*",
      "x": -120,
      "y": -160,
      "width": 240,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_resolved_ymmt",
      "type": "text",
      "text": "## ✓ Resolved\n`car_id_method = ymmt_match`\n*(or rule_applied if rules transformed)*\nconfidence = match score",
      "x": 220,
      "y": -20,
      "width": 300,
      "height": 120,
      "color": "4"
    },
    {
      "id": "n_discrepancy",
      "type": "text",
      "text": "## ✗ MappingDiscrepancy\n`status = unresolved`\nfuzzy scores + raw data stored\nfor admin review",
      "x": -460,
      "y": -20,
      "width": 300,
      "height": 120,
      "color": "1"
    }
  ],
  "edges": [
    {"id": "e1",  "fromNode": "n_entry",      "toNode": "n_vin_valid",   "fromSide": "bottom", "toSide": "top"},
    {"id": "e2",  "fromNode": "n_vin_valid",   "toNode": "n_decode",      "fromSide": "bottom", "toSide": "top",    "label": "yes"},
    {"id": "e3",  "fromNode": "n_vin_valid",   "toNode": "n_rule_engine", "fromSide": "left",   "toSide": "top",    "label": "no — skip VIN path", "color": "1"},
    {"id": "e4",  "fromNode": "n_decode",      "toNode": "n_vcache",      "fromSide": "right",  "toSide": "left",   "label": "check / cache result"},
    {"id": "e5",  "fromNode": "n_decode",      "toNode": "n_nhtsa",       "fromSide": "right",  "toSide": "left",   "label": "cache miss → fetch"},
    {"id": "e6",  "fromNode": "n_decode",      "toNode": "n_pi_resolve",  "fromSide": "bottom", "toSide": "top",    "label": "decoded (make + model + year)"},
    {"id": "e7",  "fromNode": "n_decode",      "toNode": "n_rule_engine", "fromSide": "left",   "toSide": "top",    "label": "decode failed / None", "color": "1"},
    {"id": "e8",  "fromNode": "n_pi_resolve",  "toNode": "n_resolved_vin","fromSide": "right",  "toSide": "left",   "label": "match found"},
    {"id": "e9",  "fromNode": "n_pi_resolve",  "toNode": "n_rule_engine", "fromSide": "bottom", "toSide": "top",    "label": "no PI match"},
    {"id": "e10", "fromNode": "n_rule_engine", "toNode": "n_ymmt",        "fromSide": "bottom", "toSide": "top"},
    {"id": "e11", "fromNode": "n_ymmt",        "toNode": "n_resolved_ymmt","fromSide": "right", "toSide": "left",   "label": "match ≥ 0.85"},
    {"id": "e12", "fromNode": "n_ymmt",        "toNode": "n_discrepancy", "fromSide": "left",   "toSide": "right",  "label": "no match", "color": "1"}
  ]
}
```

- [ ] **Step 2: Validate JSON**

```bash
python -m json.tool docs/flows/vin-mapping-pipeline.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add docs/flows/vin-mapping-pipeline.canvas
git commit -m "docs: add vin-mapping-pipeline canvas"
```

---

## Task 4: user-search-flow.canvas

**Files:**
- Create: `docs/flows/user-search-flow.canvas`

Top-to-bottom flow. User and UI nodes on the left, gyopart-api steps in the center, databases and inventory_api on the right.

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "n_user",
      "type": "text",
      "text": "## User\ngyopart.com visitor\n*(knows their zip code)*",
      "x": -500,
      "y": -900,
      "width": 220,
      "height": 100,
      "color": "6"
    },
    {
      "id": "n_ui",
      "type": "text",
      "text": "## gyopart-ui\nVite + React :5173\nCascading vehicle picker",
      "x": -200,
      "y": -900,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_picker",
      "type": "text",
      "text": "## Cascading Vehicle Picker\nYear → Make → Model → Trim → Engine\n`/v1/vehicles/{years,makes,models,trims,engines}`\n*(gyopart-api :8200)*",
      "x": -200,
      "y": -760,
      "width": 320,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_pi_db",
      "type": "text",
      "text": "## parts_interchange DB\nYear, Make, Model, Car\nPart, CarParts",
      "x": 220,
      "y": -760,
      "width": 280,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_parts_list",
      "type": "text",
      "text": "## Parts List\n`/v1/parts?car_id=N`\npaginated + filterable by category",
      "x": -200,
      "y": -600,
      "width": 300,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_user_input",
      "type": "text",
      "text": "## User Selects\nPart from list\n+ enters zip code",
      "x": -500,
      "y": -600,
      "width": 240,
      "height": 100,
      "color": "6"
    },
    {
      "id": "n_search",
      "type": "text",
      "text": "## Search Request\n`GET /v1/search?part_id=N&zip=NNNNN`\n*(gyopart-api :8200)*",
      "x": -200,
      "y": -460,
      "width": 300,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_car_ids",
      "type": "text",
      "text": "## Resolve Compatible car_ids\nLookup part_id in CarParts junction\n→ list of car_ids sharing this part",
      "x": -200,
      "y": -320,
      "width": 300,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_inv_call",
      "type": "text",
      "text": "## Call inventory_api\n`GET /inventory/search`\n`?car_ids=1,2,3&zip=48093&radius_miles=50`",
      "x": -200,
      "y": -180,
      "width": 300,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_inv_api",
      "type": "text",
      "text": "## inventory_api\nFastAPI\nInventory search service",
      "x": 220,
      "y": -180,
      "width": 260,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_inv_search",
      "type": "text",
      "text": "## Inventory Search\nzip → lat/lng *(uszipcode, offline)*\nHaversine distance filter\nQuery Vehicle WHERE car_id IN (…)",
      "x": 220,
      "y": -40,
      "width": 280,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_ji_db",
      "type": "text",
      "text": "## junkyard_inventory DB\nLocation + Vehicle\n*(car_id resolved by pipeline)*",
      "x": 560,
      "y": -40,
      "width": 280,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_results",
      "type": "text",
      "text": "## Ranked Results\nLocations sorted by distance\nwith matching vehicle lists\nand match counts per yard",
      "x": -200,
      "y": 120,
      "width": 300,
      "height": 120,
      "color": "4"
    }
  ],
  "edges": [
    {"id": "e1",  "fromNode": "n_user",      "toNode": "n_ui",        "fromSide": "right",  "toSide": "left",   "label": "browser"},
    {"id": "e2",  "fromNode": "n_ui",        "toNode": "n_picker",    "fromSide": "bottom", "toSide": "top"},
    {"id": "e3",  "fromNode": "n_picker",    "toNode": "n_pi_db",     "fromSide": "right",  "toSide": "left",   "label": "vehicle lookups"},
    {"id": "e4",  "fromNode": "n_picker",    "toNode": "n_parts_list","fromSide": "bottom", "toSide": "top"},
    {"id": "e5",  "fromNode": "n_parts_list","toNode": "n_pi_db",     "fromSide": "right",  "toSide": "left",   "label": "parts for car_id"},
    {"id": "e6",  "fromNode": "n_user_input","toNode": "n_search",    "fromSide": "right",  "toSide": "left",   "label": "part_id + zip"},
    {"id": "e7",  "fromNode": "n_search",    "toNode": "n_car_ids",   "fromSide": "bottom", "toSide": "top"},
    {"id": "e8",  "fromNode": "n_car_ids",   "toNode": "n_pi_db",     "fromSide": "right",  "toSide": "bottom", "label": "car_parts lookup"},
    {"id": "e9",  "fromNode": "n_car_ids",   "toNode": "n_inv_call",  "fromSide": "bottom", "toSide": "top",    "label": "car_ids resolved"},
    {"id": "e10", "fromNode": "n_inv_call",  "toNode": "n_inv_api",   "fromSide": "right",  "toSide": "left"},
    {"id": "e11", "fromNode": "n_inv_api",   "toNode": "n_inv_search","fromSide": "bottom", "toSide": "top"},
    {"id": "e12", "fromNode": "n_inv_search","toNode": "n_ji_db",     "fromSide": "right",  "toSide": "left",   "label": "vehicle query"},
    {"id": "e13", "fromNode": "n_inv_search","toNode": "n_results",   "fromSide": "left",   "toSide": "right",  "label": "sorted locations"},
    {"id": "e14", "fromNode": "n_results",   "toNode": "n_ui",        "fromSide": "top",    "toSide": "bottom", "label": "rendered list"}
  ]
}
```

- [ ] **Step 2: Validate JSON**

```bash
python -m json.tool docs/flows/user-search-flow.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add docs/flows/user-search-flow.canvas
git commit -m "docs: add user-search-flow canvas"
```

---

## Task 5: scraper-ingestion.canvas

**Files:**
- Create: `docs/flows/scraper-ingestion.canvas`

Top-to-bottom flow. Junkyard website on the left (external). junkyard_inventory DB on the right. Dedup decision branches: skip (red) or insert (continue).

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "n_trigger",
      "type": "text",
      "text": "## Scraper CLI\nPython scraper triggered\n*(CLI or scheduled run)*",
      "x": -140,
      "y": -900,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_site",
      "type": "text",
      "text": "## Junkyard Website\nWordPress / WP Car Manager\nCustom REST API / HTMX\nStatic HTML table",
      "x": -560,
      "y": -900,
      "width": 280,
      "height": 120,
      "color": "2"
    },
    {
      "id": "n_fetch",
      "type": "text",
      "text": "## Fetch Vehicle List\nPlatform-specific HTTP requests\n*(may require session / cookies)*",
      "x": -140,
      "y": -760,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_parse",
      "type": "text",
      "text": "## Parse Vehicle Record\nyear, make, model, trim\nVIN, row, section, location name",
      "x": -140,
      "y": -620,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_loc",
      "type": "text",
      "text": "## Lookup / Create Location\njunkyard_common\nLocation table in junkyard_inventory",
      "x": 240,
      "y": -700,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_dedup",
      "type": "text",
      "text": "VIN already in Vehicle\nfor this Location?",
      "x": -100,
      "y": -480,
      "width": 200,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_skip",
      "type": "text",
      "text": "## Skip\n*(already ingested)*",
      "x": 240,
      "y": -480,
      "width": 200,
      "height": 80,
      "color": "1"
    },
    {
      "id": "n_insert",
      "type": "text",
      "text": "## Insert Vehicle\njunkyard_common ORM models\n`car_id_resolved = false`\n*(enters pipeline queue)*",
      "x": -140,
      "y": -360,
      "width": 280,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_srun",
      "type": "text",
      "text": "## Update ScrapeRun\nvehicle_count++\ntimestamp updated",
      "x": -140,
      "y": -200,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_ji_db",
      "type": "text",
      "text": "## junkyard_inventory DB\nLocation + Vehicle + ScrapeRun\n*(Postgres via junkyard_common)*",
      "x": 240,
      "y": -360,
      "width": 300,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_queue",
      "type": "text",
      "text": "## Pipeline Queue\nNew vehicles with\n`car_id_resolved = false`\nready for mapping pipeline",
      "x": -140,
      "y": -60,
      "width": 280,
      "height": 120,
      "color": "3"
    }
  ],
  "edges": [
    {"id": "e1",  "fromNode": "n_trigger", "toNode": "n_site",   "fromSide": "left",   "toSide": "right",  "label": "HTTP requests"},
    {"id": "e2",  "fromNode": "n_site",    "toNode": "n_fetch",  "fromSide": "right",  "toSide": "left",   "label": "vehicle list"},
    {"id": "e3",  "fromNode": "n_fetch",   "toNode": "n_parse",  "fromSide": "bottom", "toSide": "top"},
    {"id": "e4",  "fromNode": "n_parse",   "toNode": "n_loc",    "fromSide": "right",  "toSide": "top",    "label": "yard info"},
    {"id": "e5",  "fromNode": "n_parse",   "toNode": "n_dedup",  "fromSide": "bottom", "toSide": "top"},
    {"id": "e6",  "fromNode": "n_loc",     "toNode": "n_ji_db",  "fromSide": "bottom", "toSide": "top",    "label": "get_or_create"},
    {"id": "e7",  "fromNode": "n_dedup",   "toNode": "n_skip",   "fromSide": "right",  "toSide": "left",   "label": "yes"},
    {"id": "e8",  "fromNode": "n_dedup",   "toNode": "n_insert", "fromSide": "bottom", "toSide": "top",    "label": "no"},
    {"id": "e9",  "fromNode": "n_insert",  "toNode": "n_ji_db",  "fromSide": "right",  "toSide": "left",   "label": "insert"},
    {"id": "e10", "fromNode": "n_insert",  "toNode": "n_srun",   "fromSide": "bottom", "toSide": "top"},
    {"id": "e11", "fromNode": "n_srun",    "toNode": "n_ji_db",  "fromSide": "right",  "toSide": "bottom", "label": "update"},
    {"id": "e12", "fromNode": "n_insert",  "toNode": "n_queue",  "fromSide": "bottom", "toSide": "top",    "label": "new vehicle"}
  ]
}
```

- [ ] **Step 2: Validate JSON**

```bash
python -m json.tool docs/flows/scraper-ingestion.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add docs/flows/scraper-ingestion.canvas
git commit -m "docs: add scraper-ingestion canvas"
```

---

## Task 6: admin-discrepancy-resolution.canvas

**Files:**
- Create: `docs/flows/admin-discrepancy-resolution.canvas`

Top-to-bottom flow. Two resolution paths: LLM-assisted rule creation (main path) and manual override (side path). Claude API on the right as external.

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "n_disc",
      "type": "text",
      "text": "## MappingDiscrepancy\n`status = unresolved`\n*(created by mapping pipeline)*",
      "x": -160,
      "y": -900,
      "width": 320,
      "height": 100,
      "color": "1"
    },
    {
      "id": "n_admin",
      "type": "text",
      "text": "## Admin\nX-Admin-Key auth",
      "x": -540,
      "y": -900,
      "width": 220,
      "height": 80,
      "color": "6"
    },
    {
      "id": "n_admin_ui",
      "type": "text",
      "text": "## /admin/ui/discrepancies\nadmin_api :8101 *(HTMX)*\nLists unresolved discrepancies",
      "x": -160,
      "y": -760,
      "width": 320,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_llm",
      "type": "text",
      "text": "## LLM Suggester\nClaude API via ANTHROPIC_MODEL env\nGenerates MappingRule suggestion\n`is_active = false, created_by = llm_suggested`",
      "x": -160,
      "y": -620,
      "width": 320,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_claude",
      "type": "text",
      "text": "## Claude API\n*(Anthropic)*\nmodel = ANTHROPIC_MODEL env",
      "x": 260,
      "y": -620,
      "width": 260,
      "height": 100,
      "color": "2"
    },
    {
      "id": "n_confidence",
      "type": "text",
      "text": "Confidence ≥ 0.80?",
      "x": -100,
      "y": -460,
      "width": 200,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_llm_queue",
      "type": "text",
      "text": "## /admin/ui/llm-queue\nRule shown for approval\n`is_active = false`",
      "x": 260,
      "y": -460,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_manual_review",
      "type": "text",
      "text": "## Manual Review\nShown for human inspection\n*(low confidence suggestion)*",
      "x": -540,
      "y": -460,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_approve",
      "type": "text",
      "text": "Admin approves rule?",
      "x": -100,
      "y": -320,
      "width": 200,
      "height": 80,
      "color": "3"
    },
    {
      "id": "n_activate",
      "type": "text",
      "text": "## Rule Activated\n`is_active = true`\nreprocess_job triggered",
      "x": 260,
      "y": -180,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_reject",
      "type": "text",
      "text": "## Rule Deleted",
      "x": -540,
      "y": -180,
      "width": 220,
      "height": 80,
      "color": "1"
    },
    {
      "id": "n_reprocess",
      "type": "text",
      "text": "## reprocess_job\nRe-runs mapping pipeline\non all affected vehicles",
      "x": 260,
      "y": -40,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_resolved_rule",
      "type": "text",
      "text": "## ✓ Resolved via Rule\ncar_id assigned by pipeline\nMappingDiscrepancy closed",
      "x": 260,
      "y": 100,
      "width": 280,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_manual_override",
      "type": "text",
      "text": "## Manual Override\nAdmin assigns car_id directly\n`MappingDiscrepancy.status = manual`\n→ Resolved immediately",
      "x": -820,
      "y": -760,
      "width": 280,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_resolved_manual",
      "type": "text",
      "text": "## ✓ Resolved (manual)\n`status = manual`\ncar_id set directly on Vehicle",
      "x": -820,
      "y": -600,
      "width": 280,
      "height": 80,
      "color": "4"
    }
  ],
  "edges": [
    {"id": "e1",  "fromNode": "n_admin",          "toNode": "n_admin_ui",       "fromSide": "right",  "toSide": "left"},
    {"id": "e2",  "fromNode": "n_disc",            "toNode": "n_admin_ui",       "fromSide": "bottom", "toSide": "top"},
    {"id": "e3",  "fromNode": "n_admin_ui",        "toNode": "n_llm",            "fromSide": "bottom", "toSide": "top",   "label": "trigger suggestion"},
    {"id": "e4",  "fromNode": "n_llm",             "toNode": "n_claude",         "fromSide": "right",  "toSide": "left",  "label": "API call"},
    {"id": "e5",  "fromNode": "n_llm",             "toNode": "n_confidence",     "fromSide": "bottom", "toSide": "top",   "label": "rule + confidence score"},
    {"id": "e6",  "fromNode": "n_confidence",      "toNode": "n_llm_queue",      "fromSide": "right",  "toSide": "left",  "label": "yes"},
    {"id": "e7",  "fromNode": "n_confidence",      "toNode": "n_manual_review",  "fromSide": "left",   "toSide": "right", "label": "no", "color": "1"},
    {"id": "e8",  "fromNode": "n_llm_queue",       "toNode": "n_approve",        "fromSide": "bottom", "toSide": "right", "label": "admin reviews"},
    {"id": "e9",  "fromNode": "n_approve",         "toNode": "n_activate",       "fromSide": "right",  "toSide": "left",  "label": "yes"},
    {"id": "e10", "fromNode": "n_approve",         "toNode": "n_reject",         "fromSide": "left",   "toSide": "right", "label": "no", "color": "1"},
    {"id": "e11", "fromNode": "n_activate",        "toNode": "n_reprocess",      "fromSide": "bottom", "toSide": "top"},
    {"id": "e12", "fromNode": "n_reprocess",       "toNode": "n_resolved_rule",  "fromSide": "bottom", "toSide": "top"},
    {"id": "e13", "fromNode": "n_admin_ui",        "toNode": "n_manual_override","fromSide": "left",   "toSide": "right", "label": "manual override path"},
    {"id": "e14", "fromNode": "n_manual_override", "toNode": "n_resolved_manual","fromSide": "bottom", "toSide": "top"}
  ]
}
```

- [ ] **Step 2: Validate JSON**

```bash
python -m json.tool docs/flows/admin-discrepancy-resolution.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add docs/flows/admin-discrepancy-resolution.canvas
git commit -m "docs: add admin-discrepancy-resolution canvas"
```

---

## Task 7: system-architecture.canvas (hub)

**Files:**
- Create: `docs/architecture/system-architecture.canvas`

The hub canvas. Contains all major system components, data flow edges, and a "Dive Deeper" group with file-link nodes to the other five canvases. Built last so file-link targets exist. File paths are vault-root-relative — assumes `docs/` is opened as the Obsidian vault root.

- [ ] **Step 1: Write the canvas file**

```json
{
  "nodes": [
    {
      "id": "n_user",
      "type": "text",
      "text": "## User\ngyopart.com visitor",
      "x": -1400,
      "y": -130,
      "width": 220,
      "height": 80,
      "color": "6"
    },
    {
      "id": "n_ui",
      "type": "text",
      "text": "## gyopart-ui\nVite + React\n:5173",
      "x": -1100,
      "y": -130,
      "width": 260,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_api",
      "type": "text",
      "text": "## gyopart-api\nFastAPI\n:8200",
      "x": -720,
      "y": -130,
      "width": 260,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_pi_db",
      "type": "text",
      "text": "## parts_interchange DB\nYear / Make / Model / Car\nPart / CarParts",
      "x": -280,
      "y": -280,
      "width": 300,
      "height": 100,
      "color": "4"
    },
    {
      "id": "n_inv_api",
      "type": "text",
      "text": "## inventory_api\nFastAPI\nInventory search",
      "x": -720,
      "y": 150,
      "width": 260,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_ji_db",
      "type": "text",
      "text": "## junkyard_inventory DB\nLocation / Vehicle\nMappingRule / MappingDiscrepancy\nScrapeRun / VinCache",
      "x": -280,
      "y": 150,
      "width": 300,
      "height": 140,
      "color": "4"
    },
    {
      "id": "n_admin",
      "type": "text",
      "text": "## Admin\nX-Admin-Key auth",
      "x": -1400,
      "y": 380,
      "width": 220,
      "height": 80,
      "color": "6"
    },
    {
      "id": "n_admin_api",
      "type": "text",
      "text": "## admin_api\nFastAPI + HTMX\n:8101",
      "x": -1100,
      "y": 380,
      "width": 260,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_claude",
      "type": "text",
      "text": "## Claude API\n(Anthropic)\nLLM rule suggestions",
      "x": -720,
      "y": 380,
      "width": 260,
      "height": 100,
      "color": "2"
    },
    {
      "id": "n_pipeline",
      "type": "text",
      "text": "## Mapping Pipeline CLI\npipeline/resolution_pipeline.py\nVIN decode → rule engine → YMMT",
      "x": -1100,
      "y": 620,
      "width": 300,
      "height": 120,
      "color": "5"
    },
    {
      "id": "n_scrapers",
      "type": "text",
      "text": "## Junkyard Scrapers\njunkyard-inventory-scrapers/\nPer-yard Python scrapers",
      "x": -1400,
      "y": 620,
      "width": 280,
      "height": 100,
      "color": "5"
    },
    {
      "id": "n_nhtsa",
      "type": "text",
      "text": "## NHTSA vpic API\nvpic.nhtsa.dot.gov\nVIN decode (cached)",
      "x": -720,
      "y": 620,
      "width": 280,
      "height": 100,
      "color": "2"
    },
    {
      "id": "n_websites",
      "type": "text",
      "text": "## Junkyard Websites\nWordPress / Custom REST\nHTMX / Static HTML",
      "x": -1400,
      "y": 800,
      "width": 280,
      "height": 100,
      "color": "2"
    },
    {
      "id": "grp_platform",
      "type": "group",
      "label": "junkyard-platform",
      "x": -800,
      "y": 80,
      "width": 440,
      "height": 720
    },
    {
      "id": "grp_links",
      "type": "group",
      "label": "Dive Deeper",
      "x": -1420,
      "y": 1020,
      "width": 1480,
      "height": 220
    },
    {
      "id": "fl_datamodel",
      "type": "file",
      "file": "architecture/data-model.canvas",
      "x": -1400,
      "y": 1040,
      "width": 260,
      "height": 160
    },
    {
      "id": "fl_vin",
      "type": "file",
      "file": "flows/vin-mapping-pipeline.canvas",
      "x": -1120,
      "y": 1040,
      "width": 280,
      "height": 160
    },
    {
      "id": "fl_search",
      "type": "file",
      "file": "flows/user-search-flow.canvas",
      "x": -820,
      "y": 1040,
      "width": 280,
      "height": 160
    },
    {
      "id": "fl_scraper",
      "type": "file",
      "file": "flows/scraper-ingestion.canvas",
      "x": -520,
      "y": 1040,
      "width": 280,
      "height": 160
    },
    {
      "id": "fl_admin",
      "type": "file",
      "file": "flows/admin-discrepancy-resolution.canvas",
      "x": -220,
      "y": 1040,
      "width": 320,
      "height": 160
    }
  ],
  "edges": [
    {"id": "e1",  "fromNode": "n_user",     "toNode": "n_ui",       "fromSide": "right",  "toSide": "left",   "label": "browser"},
    {"id": "e2",  "fromNode": "n_ui",       "toNode": "n_api",      "fromSide": "right",  "toSide": "left",   "label": "API calls"},
    {"id": "e3",  "fromNode": "n_api",      "toNode": "n_pi_db",    "fromSide": "right",  "toSide": "left",   "label": "vehicles + parts"},
    {"id": "e4",  "fromNode": "n_api",      "toNode": "n_inv_api",  "fromSide": "bottom", "toSide": "top",    "label": "car_ids + zip + radius"},
    {"id": "e5",  "fromNode": "n_inv_api",  "toNode": "n_ji_db",    "fromSide": "right",  "toSide": "left",   "label": "vehicle search"},
    {"id": "e6",  "fromNode": "n_admin",    "toNode": "n_admin_api","fromSide": "right",  "toSide": "left"},
    {"id": "e7",  "fromNode": "n_admin_api","toNode": "n_ji_db",    "fromSide": "right",  "toSide": "bottom", "label": "discrepancies + rules"},
    {"id": "e8",  "fromNode": "n_admin_api","toNode": "n_claude",   "fromSide": "right",  "toSide": "left",   "label": "rule suggestions"},
    {"id": "e9",  "fromNode": "n_pipeline", "toNode": "n_ji_db",    "fromSide": "right",  "toSide": "bottom", "label": "car_id resolution"},
    {"id": "e10", "fromNode": "n_pipeline", "toNode": "n_pi_db",    "fromSide": "right",  "toSide": "bottom", "label": "YMMT lookup"},
    {"id": "e11", "fromNode": "n_pipeline", "toNode": "n_nhtsa",    "fromSide": "right",  "toSide": "left",   "label": "VIN decode"},
    {"id": "e12", "fromNode": "n_scrapers", "toNode": "n_websites", "fromSide": "bottom", "toSide": "top",    "label": "HTTP scrape"},
    {"id": "e13", "fromNode": "n_scrapers", "toNode": "n_ji_db",    "fromSide": "right",  "toSide": "bottom", "label": "vehicles"}
  ]
}
```

- [ ] **Step 2: Verify all file-link targets exist**

```bash
test -f docs/architecture/data-model.canvas && echo "data-model ✓" || echo "data-model MISSING"
test -f docs/flows/vin-mapping-pipeline.canvas && echo "vin-mapping ✓" || echo "vin-mapping MISSING"
test -f docs/flows/user-search-flow.canvas && echo "user-search ✓" || echo "user-search MISSING"
test -f docs/flows/scraper-ingestion.canvas && echo "scraper ✓" || echo "scraper MISSING"
test -f docs/flows/admin-discrepancy-resolution.canvas && echo "admin ✓" || echo "admin MISSING"
```

Expected: all five lines show `✓`

- [ ] **Step 3: Validate JSON**

```bash
python -m json.tool docs/architecture/system-architecture.canvas > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/system-architecture.canvas
git commit -m "docs: add system-architecture hub canvas with links to all flows"
```

---

## Self-Review Notes

- All six canvas files create `nodes` + `edges` arrays — valid Obsidian Canvas JSON structure ✓
- Node IDs referenced in edges exist as nodes in each canvas ✓
- File-link paths in system-architecture.canvas use `architecture/` and `flows/` prefixes, vault-root-relative ✓
- Color values are strings `"1"`–`"6"` (not integers) ✓
- Task 6 coordinate collision fixed: `n_manual_override` and `n_resolved_manual` moved to x=-820 so they don't overlap with `n_manual_review` (x=-540). ✓
- Task 6 has no step to commit after writing — it has a Step 3 commit. ✓
- No TBDs or placeholders present ✓
