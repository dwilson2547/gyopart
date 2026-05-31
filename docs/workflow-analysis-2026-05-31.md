# Workflow Analysis — Gyopart UI
**Date:** 2026-05-31
**Verdict:** FAILS BASELINE

---

## Summary

Gyopart has two distinct UIs: a React/Tailwind end-user search interface (`gyopart.local`) and an HTMX/Jinja2 admin tool (`admin.gyopart.local`). The end-user UI can complete its single intended workflow — select a vehicle, pick a part, search nearby junkyards — but it is riddled with paper cuts that make repeated use frustrating: all state evaporates on refresh, the ZIP/radius resets every time you switch parts, the parts list silently truncates at 25 with no pagination, and large backend feature surfaces (part diagrams, categories, compatible-car cross-reference) are completely absent from the UI. The admin UI is more functional but has an unfixable data-entry bug (scope=source with no source field), silently broken LLM queue metrics, and zero visibility into scrape history, active locations, or the vehicle inventory itself. Neither UI has any search capability that scales past a few hundred records.

---

## Baseline Checklist Results

| Item | Result | Note |
|------|--------|------|
| Core workflow completes end-to-end | Fail | Works but with multiple degrading paper cuts |
| State survives page refresh | Fail | In-memory reducer only; full reset on refresh |
| All backend fields exposed in UI | Fail | Part description/other_names, diagrams, categories, compatible cars all missing |
| Forms show loading state | Fail | VehiclePicker selects silently populate; no spinner |
| Forms show error state | Fail | Silent failures on cars=[] and API errors |
| Lists have empty state | Pass | PartsList shows "No parts found." |
| Lists have pagination | Fail | PartsList silently truncates at 25; no page controls |
| Lists have search or filter | Partial | PartsList has filter; no search anywhere else |
| Mutations reflect immediately | Pass | HTMX admin swaps work correctly |
| No raw ID/slug inputs required | Pass | Both UIs use dropdowns/API lookups |
| Related entities browseable inline | Fail | Can't browse from yard → vehicle detail; rules aren't linked to discrepancies |
| Keyboard accessible (Enter, Escape) | Partial | ZipInput Enter works; VehiclePicker selects don't advance focus |
| Success feedback on forms | Partial | Admin rule save shows green tick; gyopart search result is feedback |
| Error feedback on forms | Fail | Silent failure if cars endpoint returns empty; admin rule 422 errors not shown in UI |
| No unbounded lists without search | Fail | Rules, LLM Queue, discrepancies tables grow unbounded with no search |
| Navigation state preserved on back | Fail | No router; one-page app loses position on refresh |

---

## Entity + Relationship Coverage

### gyopart-ui (end-user)

| Entity | Backend Fields | Fields Shown in UI | Fields Missing from UI |
|--------|---------------|-------------------|------------------------|
| Year | id, name | name (dropdown) | — |
| Make | id, name | name (dropdown) | — |
| Model | id, name, make_id | name (dropdown) | — |
| Trim | id, name | name (dropdown) | — |
| Engine | id, name | name (dropdown) | — |
| Car | id, year_id, make_id, model_id, trim_id, engine_id | used internally | — |
| Part | id, title, part_number, description, other_names | title, part_number | **description, other_names** |
| Category | id, name | **not exposed** | **all fields** |
| Diagram | id, category_id, sub_category_id, image_id | **not exposed** | **all fields** |
| YardResult | name, address, city, state, zip, phone, distance, matching_vehicles | all shown | — |
| VehicleResult | year, make, model, trim, row | all shown | car_id (internal) |

**Missing relationships:**
- Part → Categories/Diagrams: `GET /v1/categories?car_id=` and `GET /v1/categories/{id}/diagrams` exist; not wired up.
- Part → Compatible Cars: `GET /v1/parts/{part_id}/compatible-cars` exists; not used.
- Part detail view: `GET /v1/parts/{part_id}` with description/other_names is never called for display.

### admin-ui (admin)

| Entity | Backend Fields | Fields Shown in UI | Fields Missing from UI |
|--------|---------------|-------------------|------------------------|
| MappingDiscrepancy | id, vehicle_id, raw_make/model/trim, fuzzy scores, candidate_car_id, status, resolved_at | all relevant fields | resolved_car_id, resolved_by_rule_id |
| MappingRule | id, scope, source, field, rule_type, raw_value, canonical_value, make_context, priority, is_active, created_by, applied_count, llm_confidence, llm_rationale | most fields | **priority not in list view**, source field not in create form |
| Location | id, source, name, chain, address, city, state, zip, phone, lat, lng, is_active | **not exposed** | **all fields** |
| Vehicle | 30+ fields including vin, mileage, engine details, car_id status | **not exposed as browse** | **all fields** |
| ScrapeRun | id, source, started_at, completed_at, total_in_feed, new/updated/removed vehicles, success, error_message | **not exposed** | **all fields** |
| VinCache | vin, make, model, model_year, trim, error_code, fetched_at | NHTSA decode shown in discrepancy context | direct browse missing |

---

## Workflow Coverage by Persona

### Persona: End User (searching for a part at a junkyard)

| # | Workflow | Status | Notes |
|---|----------|--------|-------|
| 1 | Select vehicle by year/make/model/trim/engine | ✅ | Works, but 5 sequential dependent selects with no type-ahead is slow |
| 2 | Search parts for my vehicle | ⚠️ | Works but silently truncated at 25; no pagination; total shown nowhere |
| 3 | Filter parts by keyword | ⚠️ | Fires API call on every keystroke (no debounce); filter works |
| 4 | Select a part and search nearby junkyards | ✅ | Core workflow complete |
| 5 | Change search radius | ⚠️ | Works once, but radius/zip reset when switching to a different part |
| 6 | View part description or alternate names | ❌ | description and other_names exist in API response but are never displayed |
| 7 | Browse part diagrams for my vehicle | ❌ | `/v1/categories` and `/v1/diagrams` exist but are not wired to UI |
| 8 | Deselect a part and start over | ❌ | CLEAR_PART action exists in context but no button triggers it |
| 9 | Return to app after refresh | ❌ | All state lost; must restart from year selection |
| 10 | Know when parts list is truncated | ❌ | API returns `total` but UI never displays it; user sees 25 items with no indication |

### Persona: Admin (resolving mapping discrepancies)

| # | Workflow | Status | Notes |
|---|----------|--------|-------|
| 1 | View unresolved discrepancy groups | ✅ | Works well; fuzzy matches and NHTSA decode shown |
| 2 | Create a mapping rule from a discrepancy | ✅ | Inline form works; NHTSA autofill buttons helpful |
| 3 | Ignore a discrepancy group | ✅ | Inline HTMX, row removed on confirm |
| 4 | Create a source-scoped rule | ❌ | Scope=source has no corresponding source input in create form; source field is hidden and empty |
| 5 | Search discrepancies by make/model/source | ❌ | No search; only tab filter by status |
| 6 | View rules and verify they applied | ⚠️ | applied_count is shown but priority and source are not in the list view; have to edit to see |
| 7 | Edit an existing rule | ✅ | Inline HTMX edit form works |
| 8 | Deactivate a rule | ✅ | Works; row is replaced with success response |
| 9 | Review LLM rule suggestions | ⚠️ | Page works but affected_count is hardcoded to 0 for all suggestions (backend bug) |
| 10 | Approve an LLM suggestion | ✅ | Works; triggers background reprocess |
| 11 | Reject an LLM suggestion | ⚠️ | Sends POST but row swapped to empty response — no confirmation, row disappears silently |
| 12 | Run the resolution pipeline | ⚠️ | Button exists; status span shows API response text but no progress or error handling |
| 13 | View scrape history | ❌ | No UI; ScrapeRun table exists in DB but is invisible |
| 14 | Browse and search vehicle inventory | ❌ | No UI; Vehicle table exists but is inaccessible |
| 15 | Manage locations (activate/deactivate) | ❌ | No UI; Location.is_active exists but no management surface |
| 16 | Restore an ignored discrepancy | ❌ | No "un-ignore" action in the Ignored tab |
| 17 | Delete a mapping rule permanently | ❌ | Only deactivate is available |

---

## Anti-Pattern Audit Results

### gyopart-ui

| Anti-Pattern | Location | Severity |
|---|---|---|
| **State not persisted** — full app reset on page refresh | App-wide (useReducer, no localStorage) | P0 |
| **Silent truncation** — PartsList shows 25 items with no pagination or count display; user has no idea the list is incomplete | PartsList component | P0 |
| **Form clears on context change** — ZipInput `key={state.activePart.id}` resets ZIP and radius every time a new part is selected | ZipInput | P1 |
| **Silent failure on empty cars** — `handleSetActive()` silently returns if `cars.length === 0`; user has no feedback | VehiclePicker `handleSetActive()` | P1 |
| **No loading state in VehiclePicker** — depends selects show as enabled before data loads; user can select stale placeholder | VehiclePicker selects | P1 |
| **No part detail view** — `description` and `other_names` are fetched but never displayed | PartsList, App state | P1 |
| **No way to clear active part** — CLEAR_PART exists in context reducer but no UI trigger | App layout | P1 |
| **No debounce on filter** — every keystroke fires a network request | PartsList filter input | P2 |
| **Diagrams/categories absent** — entire category+diagram feature surface has no UI entry point | App-wide | P1 |
| **TopBar title "Parts Interchange"** — internal data product name exposed as the app's identity | TopBar | P2 |

### admin-ui

| Anti-Pattern | Location | Severity |
|---|---|---|
| **Source-scoped rules broken** — `scope` dropdown includes "source" but the `source` field is hidden and always empty in the create form on Rules page; source-scoped rules are impossible to create correctly without directly using the API | Rules create form | P0 |
| **LLM affected_count hardcoded to 0** — backend code always sets `"affected_count": 0` before returning to template; metric is permanently misleading | LLM Queue page, `admin_api/main.py:ui_llm_queue()` | P1 |
| **LLM reject is silent** — rejecting a suggestion swaps the row to an empty HTTP 200 response with no content; the row disappears with no confirmation or undo | LLM Queue, `_rule_row.html` swap | P1 |
| **Discrepancy table has no search** — only status-tab filtering; for large datasets this table is unusable | Discrepancies page | P1 |
| **Rules table has no search or sort** — unbounded list with no ability to find a specific rule | Rules page | P1 |
| **Priority hidden from rules list view** — priority field is in DB and edit form but not displayed in table; can't audit rule ordering without editing each row | Rules table `_rule_row.html` | P1 |
| **No scrape history UI** — `ScrapeRun` table exists with all stats but is not surfaced anywhere | Admin app-wide | P1 |
| **No location management UI** — `Location.is_active` exists; no way to disable a source/location without direct DB access | Admin app-wide | P1 |
| **No vehicle browser** — no way to find a specific vehicle, check its `car_id_method`, or browse inventory | Admin app-wide | P2 |
| **No pagination on any table** — all three admin pages load full result sets; will degrade as data grows | All admin pages | P2 |
| **No "un-ignore" action** — once a discrepancy group is ignored, no UI path to restore it | Discrepancies "Ignored" tab | P2 |

---

## Prioritized Gap List

### P0 — Workflow Blockers

1. **[gyopart-ui] State lost on refresh.** The entire app resets to the year picker on any page refresh. No partial vehicle selection, active part, ZIP code, or search results survive. Correct behavior: persist `selectedVehicle`, `activePart`, `zip`, and `radiusMiles` to `localStorage` and rehydrate on mount.

2. **[gyopart-ui] PartsList silently truncates at 25.** The API returns `total` in `PagedPartsResponse` but the component ignores it. A vehicle with 300+ compatible parts shows 25 with no indicator. Correct behavior: display total count, show current range ("1–25 of 312"), and add prev/next page controls that call `api.parts(carId, filter, page)`.

3. **[admin-ui] Source-scoped rules are uncreateable via the UI.** The Rules create form has a `scope` select with a "source" option, but the `source` text field is not present. Any rule created with scope=source has `source=NULL` in the database, which means it behaves as a global rule but is tagged incorrectly. Correct behavior: show a "Source" text input that becomes enabled when scope=source is selected (same pattern as the discrepancy inline form already uses).

### P1 — High Friction

4. **[gyopart-ui] ZIP/radius reset on every part switch.** `ZipInput` uses `key={state.activePart.id}`, which unmounts and remounts the component on every part selection, destroying entered ZIP and radius. Correct behavior: remove the `key` prop; let the ZIP and radius persist across part selections.

5. **[gyopart-ui] Silent failure on empty car resolution.** If `api.cars()` returns an empty array, `handleSetActive()` silently returns. The user sees nothing happen after clicking "Set Active Vehicle" with a fully resolved selection. Correct behavior: show an error message in the VehiclePicker: "No catalog entry found for this exact configuration."

6. **[gyopart-ui] No loading state in VehiclePicker selects.** Between user selection and dependent data loading, the next select appears enabled but empty. Correct behavior: set the dependent select to `disabled` during fetch and add a placeholder option "Loading…" while the request is in flight; the hook already sets the array to `[]` before fetching, just needs a `loading` flag per level.

7. **[gyopart-ui] Part description and other_names never shown.** The API returns these on both the list and detail endpoints. For a user trying to confirm they have the right part, these are essential. Correct behavior: show `description` below the part title in the PartsList (truncated with tooltip/expand), or open a part detail panel when a part is clicked.

8. **[gyopart-ui] No way to deselect an active part.** Once a part is selected, the left rail shows only the PartsList. To go back to searching for a different part, the user must click "Change" on the vehicle header (which clears the vehicle too) or manually reload. Correct behavior: add a small "✕" or "Clear" button next to the active part highlight that dispatches `CLEAR_PART`.

9. **[gyopart-ui] Diagrams and categories are absent.** The backend has a complete category→diagram→parts hierarchy with image URLs. For the parts-search use case, showing a schematic image with callouts is the best way to confirm the right part. Correct behavior: add a "Diagrams" tab or secondary view under the vehicle header, pulling from `GET /v1/categories?car_id=` and `GET /v1/categories/{id}/diagrams`.

10. **[admin-ui] LLM affected_count is hardcoded to 0.** In `admin_api/main.py:ui_llm_queue()`, `"affected_count": 0` is hardcoded for every suggestion. This value should be a count of vehicles whose discrepancy would be resolved by applying the rule. Correct behavior: query `MappingDiscrepancy` joining `Vehicle` where `source=source` and raw values match the rule pattern.

11. **[admin-ui] LLM reject is silent.** After clicking Reject, the row disappears with no feedback. `hx-swap="outerHTML"` on a 200 empty response removes the row silently. Correct behavior: return a TemplateResponse with a "rejected" inline message (same style as the rule-save success confirmation), or at minimum a strikethrough row that fades out.

12. **[admin-ui] Discrepancy table has no search.** With thousands of discrepancies, status-tab filtering alone is insufficient. Correct behavior: add a text input above the table that filters client-side by source/raw_make/raw_model, or add query parameters and re-fetch server-side.

13. **[admin-ui] Rules table has no search, no sort, missing priority column.** Correct behavior: (a) add a priority column to the rules table display (trivial template change to `_rule_row.html`); (b) add a source column (also trivial); (c) add server-side or client-side search by raw_value/canonical_value.

14. **[admin-ui] No scrape history UI.** `ScrapeRun` contains per-run stats (new, updated, removed vehicles, success, error_message). Operators have no way to see whether scrapers are running successfully without direct DB access. Correct behavior: add a "Scrapes" tab to the admin nav that lists recent `ScrapeRun` records grouped by source with latest success/failure status.

15. **[admin-ui] No location management.** `Location.is_active` allows disabling a source location, but there's no UI to toggle it. Correct behavior: add a "Locations" tab listing all locations with their source, vehicle count, last_seen_at, and an active toggle button.

### P2 — Polish

16. **[gyopart-ui] No debounce on PartsList filter.** Fires a network request on every keystroke. Add 200ms debounce.

17. **[gyopart-ui] TopBar title is "Parts Interchange"** — the name of an internal data product. Should be "Gyopart" or a user-facing app name.

18. **[admin-ui] No pagination on admin tables.** At scale all three pages load unbounded result sets. Add server-side pagination with prev/next controls.

19. **[admin-ui] No "un-ignore" for discrepancies.** An "Ignored" tab exists but there's no restore action. Add a "Restore" button that sets status back to "unresolved".

20. **[admin-ui] Rules can only be deactivated, not deleted.** For test/junk rules this creates permanent clutter. Add a hard-delete endpoint and button (with confirmation).

---

## Recommendations

### P0 fixes

**1. Persist app state to localStorage (gyopart-ui)**
In `AppContext.tsx`, wrap the initial state with a read from `localStorage` and add a `useEffect` that writes state to `localStorage` on every change. Persist `selectedVehicle`, `activePart`, `zip`, and `radiusMiles`. On mount, parse and rehydrate. The `searching` and `results` fields should not be persisted.

**2. Add pagination to PartsList (gyopart-ui)**
`PartsList.tsx`: add `page` state (default 1). Display `total` from the API response. Add a prev/next button row below the list, disabled when at bounds. Render `Showing 1–25 of {total}` above the list. The `api.parts()` call already accepts a `page` parameter.

**3. Fix source-scoped rule creation in admin Rules page**
In `rules.html` create form: add `<input name="source" id="rules-source" placeholder="e.g. lkq" style="width:120px">` and `<div id="rules-source-wrap" style="display:none">`. In `onRulesFieldChange`, toggle display of `rules-source-wrap` when scope changes to "source". Same fix needed in the discrepancy inline rule form.

### P1 fixes

**4. Remove ZipInput key prop (gyopart-ui)**  
Remove `key={state.activePart.id}` from `<ZipInput>` in `JunkyardResults.tsx`. The component should persist its ZIP/radius across part switches.

**5. Show part description in PartsList (gyopart-ui)**  
In `PartsList.tsx`, render `{p.description && <span className="text-slate-500 text-xs block truncate">{p.description}</span>}` below the part_number. Add a hover title with the full description.

**6. Add "Clear part" button (gyopart-ui)**  
In `App.tsx` or `PartsList.tsx`, add a small clear button above the list when `state.activePart` is set: `<button onClick={() => dispatch({ type: 'CLEAR_PART' })}>Clear selection</button>`.

**7. Fix LLM affected_count (admin-ui)**  
In `admin_api/main.py:ui_llm_queue()`, replace `"affected_count": 0` with a query:
```python
from sqlalchemy.orm import Session
with Session(_engine) as sess:
    count = sess.execute(
        select(func.count()).select_from(MappingDiscrepancy)
        .join(Vehicle, MappingDiscrepancy.vehicle_id == Vehicle.id)
        .where(Vehicle.source == r["source"], MappingDiscrepancy.raw_make == r["raw_value"])
    ).scalar_one()
```

**8. Add ScrapeRun history page (admin-ui)**  
Add `GET /admin/ui/scrapes` route in `admin_api/main.py`, a new `scrapes.html` template, and a "Scrapes" nav link. Query `ScrapeRun` ordered by `started_at DESC`, group by source, show last 50 runs.
