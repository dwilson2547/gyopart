# Workflow Analysis — Gyopart
**Date:** 2026-05-31  
**Verdict:** FAILS BASELINE

---

## Summary

Gyopart is a parts lookup and junkyard search tool. It has the right data (1,788 parts for a
2020 Ford EcoSport, 18 diagram categories with up to 75 diagrams each, junkyard inventory
with distance search) and the right structure (vehicle picker → parts list → junkyard search),
but the user-facing experience is functionally broken at the parts that matter most.

The most damaging issue: **search results are destroyed the moment the user selects a
different part**. Every comparison requires re-entering ZIP and re-running search from scratch.
The diagram browser is the second UX failure — it presents a list labeled "Diagram 1" through
"Diagram 75" with zero indication of what each covers, forcing the user to click them blindly.
Both problems have solutions in existing data (the reducer is a deliberate choice; subcategory
names exist in the DB). The junkyard results completes the picture: yards are shown with name,
address, and distance, but there is no map link, no website, and no directions — the user
googles the yard name to find out how to actually go get the part.

This is not a half-baked product in the sense of missing features. The features are present.
They are implemented in ways that make them unusable at the last step.

---

## Baseline Checklist Results

| Item | Status | Note |
|------|--------|------|
| All entity fields reachable from UI | ❌ FAIL | Part `description`, yard `lat/lng`, subcategory name, vehicle detail all invisible |
| No raw ID/slug inputs | ✅ PASS | Vehicle picker uses dependent dropdowns throughout |
| Required fields indicated | ✅ PASS | ZIP field disables Search until 5 digits |
| Loading states visible | ✅ PASS | "Loading…" shown in parts list and diagram panels |
| Empty states explained | ⚠️ PARTIAL | Parts list has "No parts found." but main panel has no guidance before vehicle selected |
| Error states visible | ❌ FAIL | Part load failure shows blank; search failure shows empty results silently |
| Success feedback on actions | ❌ FAIL | Selecting a part silently clears all results with no explanation |
| No filter reset on nav | ❌ FAIL | Active diagram and tab selection lost on page reload |
| Lists have search/filter | ⚠️ PARTIAL | Parts list has filter; diagram list (up to 75 items) has none |
| Mutations reflected immediately | ❌ FAIL | Results cleared on part selection with no trigger to re-search |
| No unbounded unfiltered lists | ❌ FAIL | Diagram list: up to 75 entries with no names and no filter |
| Enter submits forms | ✅ PASS | ZIP input submits on Enter |
| Tab order sensible | ✅ PASS | Vehicle picker, filter, and search controls tab sequentially |
| Escape dismisses modals | N/A | No modals in this UI |
| State persists across reload | ❌ FAIL | Vehicle/part/ZIP persisted; tab, diagram selection, and results not persisted |

---

## Entity + Relationship Coverage

### gyopart-api entities

| Entity | Backend Fields | Shown in UI | Missing from UI |
|--------|---------------|-------------|-----------------|
| Year/Make/Model/Trim/Engine | id, name | ✅ All used in picker | — |
| Car | id, all FK ids | id used internally | — |
| Part | id, title, part_number, description, other_names | title, part_number, other_names | **`description` never rendered** |
| Category | id, name | ✅ Shown (slug formatted) | — |
| Subcategory | id, name, category_id | **Never shown** | **Name exists in DB; not returned by DiagramOut schema** |
| Diagram | id, category_id, sub_category_id, image_id | id used for selection only | **sub_category name missing — shown as "Diagram 1…N"** |
| DiagramDetail | image_url, image_alt, parts[] | ✅ Shown on click | image_alt has subcategory name but not exposed in list view |
| Image | url, alt_text | ✅ Rendered | No zoom or full-screen |

### Junkyard inventory entities

| Entity | Backend Fields | Shown in UI | Missing from UI |
|--------|---------------|-------------|-----------------|
| Location | id, source, name, chain, address, city, state, zip, phone, **lat, lng**, is_active | name, address, city, state, zip, phone, distance | **lat/lng never in SearchResponse; no map link; no website; no chain** |
| Vehicle (inventory) | year, make, model, trim, vin, row, color, mileage, **preview_image_url**, drive_type, fuel_type, engine_* | year, make, model, trim, row | **color, mileage, preview_image_url, drive_type, engine all hidden** |
| ScrapeRun | started_at, completed_at, new/updated/removed counts, success, error_message | **Not exposed** | No scrape run history anywhere |

---

## Workflow Coverage by Persona

### Persona: Parts Searcher (user looking for a used part near them)

| Workflow | Status | What Breaks |
|----------|--------|-------------|
| Select a vehicle for the first time | ✅ Works | 5-step cascade picker, each step enables next on load |
| Find a part by name | ✅ Works | Filter with debounce, pagination, part number shown |
| Compare availability of two different parts | ❌ Broken | `SET_PART` clears `results[]`. Selecting part B destroys part A's search results. No history. Must re-enter ZIP and re-search every single time. |
| Return to session next day | ⚠️ Degraded | Vehicle, part, ZIP saved. Results lost. Tab and diagram selection lost. |
| Find a junkyard and get there | ⚠️ Degraded | Name, address, distance shown. No map link, no website. User must google the yard. |
| Understand what a part is before committing to a search | ❌ Broken | `description` field (e.g., "EcoSport. 1.0l. Fiesta. 1.0l.") exists in API, never rendered. User cannot confirm compatibility variant. |
| Use diagrams to identify the right part | ❌ Broken | Body category: 75 diagrams, all "Diagram 1" – "Diagram 75". Electrical: 62. User must click every entry blindly. |
| Know search is triggered with new part | ❌ Broken | Results vanish immediately; no message says "run search for this part". The Search button exists but requires the user to notice results disappeared. |

### Persona: Diagram Browser (user identifying parts by visual schematic)

| Workflow | Status | What Breaks |
|----------|--------|-------------|
| Find the diagram for a specific system | ❌ Broken | No subcategory names shown. Engine: 10 unlabeled diagrams. Electrical: 62 unlabeled. No filter. |
| View diagram at readable size | ❌ Broken | Images capped at max-h-96. Vintage GIF schematics with fine-print labels. No zoom, no lightbox, no full-screen. |
| Click a part from a diagram and search | ⚠️ Degraded | Works mechanically (switches to Parts tab + dispatches SET_PART), but clears results due to P0 issue. Must re-search. |
| Know which diagram you're currently viewing | ⚠️ Degraded | Only the `image_alt` text below the image indicates context (e.g., "Powertrain Control for 2018 Ford EcoSport"). No breadcrumb in the nav. |
| Find which diagram a known part number appears in | ❌ Broken | No reverse lookup. Must browse all diagrams manually. |

### Persona: Admin (data team resolving vehicle mapping discrepancies)

| Workflow | Status | What Breaks |
|----------|--------|-------------|
| Review unresolved discrepancies | ✅ Works | Tabbed status filter, grouped rows, fuzzy match scores shown |
| Create a mapping rule from a discrepancy | ✅ Works | Inline form, NHTSA suggestion buttons, source-scoping all work |
| Know how many vehicles a rule will fix | ❌ Broken | Affected count only shown in LLM queue, not in discrepancy rows |
| Find and edit an existing rule | ❌ Broken | No edit. Must deactivate + recreate. No search/filter on rules table. |
| Review and approve LLM suggestions | ✅ Works | Approve/reject with HTMX row feedback |
| Trigger LLM to generate suggestions | ❌ Broken | No UI button to run the LLM suggester |
| Browse locations or vehicle inventory | ❌ Broken | No UI for Location or Vehicle tables. No visibility into scraped data. |
| View scrape run history | ❌ Broken | ScrapeRun table exists; no UI. |

---

## Anti-Pattern Audit

### State and Feedback

| Anti-Pattern | Location | Severity |
|---|---|---|
| Silent destructive action | `SET_PART` clears `results[]` without explaining why — results vanish with no message | P0 |
| No success feedback | Part selection has no confirmation, no "now searching for X" state | P0 |
| No error feedback | Parts list load failure shows blank list; network error in search shows 0 results silently | P1 |
| Filter reset on nav | `leftTab`, `activeDiagramId`, `activeCategoryId` are component state, lost on reload | P1 |

### Navigation

| Anti-Pattern | Location | Severity |
|---|---|---|
| No breadcrumbs | DiagramView has no category/subcategory path indicator | P1 |
| Silent click | Category click in DiagramBrowser collapses diagrams list before re-loading — no visual transition | P2 |
| No close affordance | No way to deselect active diagram without selecting another; no ✕ on active part | P2 |
| Missing cross-navigation | No link between `admin.gyopart-dev.local` and `gyopart-dev.local` | P2 |

### List and Filter

| Anti-Pattern | Location | Severity |
|---|---|---|
| Unbounded unfiltered list | DiagramBrowser: up to 75 entries, all unlabeled | P0 |
| Unbounded unfiltered list | Admin rules table: no search; will become unusable past ~50 rules | P1 |
| Unbounded list no pagination | Admin discrepancies: no pagination; potentially thousands of rows | P1 |

### Forms

| Anti-Pattern | Location | Severity |
|---|---|---|
| Partial form — missing fields | YardCard: no map link, no directions, no website | P0 |
| Partial form — missing fields | PartsList: `description` never shown | P1 |
| Partial form — missing fields | YardCard vehicle rows: color, mileage, preview_image_url all hidden | P1 |
| No edit on existing entity | Admin rules: deactivate only, no edit | P1 |

---

## Prioritized Gap List

### P0 — Workflow Blockers

**1. Results cleared on part change.**  
`case 'SET_PART'` in the reducer sets `results: []`. Every new part click destroys all existing search results. User cannot compare two parts without re-running the full search cycle.  
**Fix:** Remove `results: []` from `SET_PART` case. Results belong to the ZIP+radius search, not the selected part. Separately, add auto-search: when `activePart` changes and `zip.length === 5`, trigger `handleSearch` automatically.

**2. Diagram list has no names.**  
Body: 75 diagrams, Electrical: 62. All labeled "Diagram 1–N". `Subcategory.name` exists in the DB. `image_alt` contains it (e.g., "Powertrain Control for 2018 Ford EcoSport") but only available after loading the full diagram detail — not in the listing.  
**Fix:** Add `sub_category_name: str | None` to `DiagramOut`. In `GET /v1/categories/{id}/diagrams`, left-join `Subcategory` and populate the field. Display it in `DiagramBrowser` instead of "Diagram N".

**3. No map link or directions from junkyard results.**  
After finding matching yards, user must manually google the yard to get there. `Location.lat` and `.lng` exist but are not in `SearchResponse`.  
**Fix:** Add `lat: float | None` and `lng: float | None` to `YardResult` schema and populate from `Location` in `inventory_api/search.py`. Render a Google Maps directions link on each `YardCard` when lat/lng are present.

**4. Diagram image has no zoom.**  
Vintage GIF schematics with fine part-label detail are capped at `max-h-96`. Users cannot read part callout numbers on complex diagrams (electrical has 62).  
**Fix:** Wrap the `<img>` in `DiagramView` with a click handler that opens a `<dialog>` (native HTML) containing the full-size image. Close on click or Escape.

### P1 — High Friction

**5. Part `description` field never shown.**  
The API returns `description` (sometimes blank, sometimes specific: "EcoSport. 1.0l. Fiesta. 1.0l. Focus. 1.0l."). It is never rendered. User cannot confirm which variant of a part fits their vehicle.  
**Fix:** In `PartsList` button, render `{p.description && <p className="...text-xs">{p.description}</p>}` below the title. Also show it in `ZipInput` next to the active part name.

**6. No auto-search on part selection.**  
User must manually click Search after selecting a new part even when ZIP is already populated. This is three unnecessary clicks (select part, focus ZIP, click Search) that could be one.  
**Fix:** In `ZipInput`, `useEffect` watching `state.activePart`: if `state.zip.length === 5`, call `handleSearch()`. Guard with a `useRef` to avoid double-firing on mount.

**7. Tab and diagram state not persisted to localStorage.**  
`leftTab` and `activeDiagramId` are component-local `useState`. Lost on every reload.  
**Fix:** Move `leftTab`, `activeDiagramId`, and `activeCategoryId` into `AppContext` and persist them to `localStorage` with the existing state.

**8. Diagram browser has no category/subcategory context while viewing.**  
While `DiagramView` is open, the left rail shows a category list that may have scrolled. No breadcrumb says "Engine → Powertrain Control".  
**Fix:** Pass `categoryName` and `subCategoryName` through to `DiagramView`. Render a two-level header above the diagram image.

**9. YardCard vehicle rows missing useful fields.**  
Color, mileage, drive type, and preview image all exist on the `Vehicle` model but are not in the search response. A user looking for "low-mileage black EcoSport" sees only year/make/model/trim/row.  
**Fix:** Add `color: str | None`, `mileage: int | None`, and `preview_image_url: str | None` to `VehicleResult` in `inventory_api/models.py`. Populate in `search.py`. Render color and mileage as secondary columns in `YardCard`.

**10. Admin rules table has no search.**  
Will become unusable past ~50 rules. No filter by field, type, raw value, or source.  
**Fix:** Add a `<input type="search">` above the rules table with JavaScript filtering on visible rows. No server roundtrip needed.

**11. Admin discrepancies has no pagination.**  
Single query returning all rows. At scale this will time out.  
**Fix:** Add `?page=` and `?per_page=50` to the discrepancies endpoint; render pagination controls.

**12. No way to trigger LLM suggestion generation from admin UI.**  
**Fix:** Add a "Run LLM Suggester" button on the LLM queue page that POSTs to a trigger endpoint and shows progress feedback.

### P2 — Polish

**13.** Diagram list filter: once subcategory names are added (P0.2), add a text filter input in `DiagramBrowser` for high-count categories.

**14.** Category scroll hint: `max-h-52` clips the category list at 18 items. Add a bottom fade gradient to indicate scrollability.

**15.** `ZipInput` part name `max-w-36` truncates long names like "Powertrain Control Module". Remove the cap or increase to `max-w-56`.

**16.** Active part deselect affordance: no ✕ button or visible "Clear" action. The click-to-deselect behavior is undiscoverable.

**17.** Add a "View User UI" link in the admin nav bar and "Admin" link in the main TopBar.

**18.** Admin rules: add an "Inactive Rules" tab to allow viewing and re-activating previously deactivated rules.

**19.** Main panel empty state: before any vehicle is selected, the right panel shows nothing. Add a centered call-to-action with brief instructions.
