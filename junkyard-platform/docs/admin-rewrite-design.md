# Junkyard admin rewrite — design

Status: **live in prod** (2026-10-15; decisions in §4, phases in §3). Nothing here is built yet. The "Today" section and the numbers are
verified against the code on `dev` (fd3f7af) and read-only queries against prod on 2026-10-15; the
rest is planned.

The admin app exists to get yard vehicles matched to catalogue cars. It should show *why* a vehicle
didn't match and let an admin fix the cause by **picking** the right catalogue value, never by typing
it, then see the fix take effect within seconds. Later it goes public behind authentik.

## 1. Today

### 1.1 How a vehicle gets matched (`pipeline/resolution_pipeline.py`, run by the vin-resolver worker)

1. **VIN decode** (NHTSA, cached in `vin_cache`) → `car_matcher.match_decoded`: catalogue cars with
   the decode's year + make + model (model compared by a loose key, plus NHTSA `Series` for Ram-style
   names), narrowed by engine/fuel/trim. Any candidates → matched (`vin_exact` / `vin_candidates`).
2. Otherwise **rules** (`mapping_rules`) rewrite the *yard's own* make/model/trim strings, then
   **fuzzy YMMT match** on those strings (`ymmt_match` / `rule_applied`).
3. Otherwise a `mapping_discrepancies` row (status `unresolved`).

The worker uses `vehicles` as its queue: a vehicle with `car_id_resolved = false AND
resolve_attempted_at IS NULL` is picked up within seconds. Clearing those fields re-resolves it.

### 1.2 Prod numbers (2026-10-15, read-only queries)

121,054 active vehicles; 102,987 matched (vin_candidates 48,952, vin_exact 47,997, ymmt_match 4,796,
rule_applied 1,242). **18,067 unmatched.** Of those:

| Why it didn't match | Vehicles | Fixable by an admin? |
|---|---|---|
| No VIN / VIN never decoded / decode error | 512 / 104 / 30 | Partly (yard-string rules) |
| Clean decode, **year not in the catalogue for that make** | 11,522 | No: catalogue coverage |
| — of which Dodge / Jeep / Chrysler (catalogue has only 2001–2009 so far) | ~9,450 | No: fills as the Mopar catalogue scrape runs |
| Clean decode, **model name not in the catalogue** for that make | 2,973 (136 distinct make/model pairs) | **Yes: name mapping** |
| Clean decode, model exists in the catalogue but **not for that year** | 2,337 | Mostly no (coverage); some naming |
| Clean decode, **make not in the catalogue** (Saab, Isuzu, Geo, …) | 589 | Sometimes (Geo → Chevrolet) |

Top name mismatches: MERCEDES-BENZ C-Class (431), E-Class (147), M-Class (133); CHEVROLET Silverado
with NHTSA series like "1500 (1/2 Ton)" / "1/2 Ton" (~500 across variants), GMT-400 (153); GMC
Sierra "1/2 Ton Nominal" (88).

**96% of unmatched vehicles have a clean NHTSA decode**, and the decode path never consults rules.
There is one rule in the system (a global exact make rule, applied 2,984 times).

### 1.3 Problems with the current app

- **Rules fix the wrong thing.** They rewrite yard strings for the fuzzy step; the 96% that fail on
  the NHTSA decode can't be fixed by any rule.
- **Typed values.** Raw value, make context, source and trim canonical value are free text; only
  make/model canonical values are dropdowns (full model list, unfiltered unless make context was
  typed first).
- **The create-rule form exposes engine internals**: field, rule type (exact/prefix/regex), scope,
  priority, make context — eight inputs to say "this means that".
- **Editing a rule can silently break it**: the edit row offers scope `source` but has no source
  input, and `update_rule` never sets `source`, so the rule then never matches.
- **Grouping by yard strings, decode from an arbitrary vehicle.** Groups are
  (source, raw make, raw model); the NHTSA column shows the first vehicle in the group that has a
  decode, though vehicles in one group can decode differently.
- **No reason shown.** Catalogue gaps (two thirds of the list) look the same as fixable mismatches.
- **Dead statuses.** `pending_rule` is only set by the LLM suggester and never reprocessed;
  `no_match_in_dataset` is never set; every prod row is `unresolved`.
- **Counts include gone vehicles**: 146 discrepancy rows belong to vehicles no longer in the yard.
- **"Run Pipeline" reprocesses everything in a web-process background task**; creating a manual rule
  doesn't trigger any reprocessing.
- **LLM suggester** calls a paid API and is disabled (`llmSuggester.enabled: false`).
- `Base.metadata.create_all` at startup in a service whose schema is owned by Alembic.
- No sign-in.

## 2. Design

### 2.1 Discrepancies carry a reason and the decode

When the worker records a discrepancy it also stores **why** and **what NHTSA said**, so grouping is
plain SQL in one database (the catalogue lives in another):

- New columns on `mapping_discrepancies`: `reason`, `nhtsa_year`, `nhtsa_make`, `nhtsa_model`,
  `nhtsa_series`.
- `reason` ∈ `no_vin`, `decode_failed`, `make_not_in_catalogue`, `year_not_in_catalogue`,
  `model_not_in_catalogue`, `model_year_gap`. Computed in `match_decoded`'s failure path from the
  same catalogue rows it already loads.
- The worker **deletes** the discrepancy row when the vehicle later matches, and the list only counts
  active vehicles.
- Statuses collapse to `open` / `ignored`. `pending_rule` / `no_match_in_dataset` go away.

### 2.2 Name mappings replace rules

A mapping says: *this NHTSA (make, model[, series]) is that catalogue make/model*. Exact match on the
loose name key only; no prefix/regex, no priority, no scope in the UI.

- Table `decode_mappings`: `nhtsa_make`, `nhtsa_model`, `nhtsa_series` (nullable = any),
  `year_from` / `year_to` (nullable = all years), `catalogue_make`, `catalogue_model`,
  `created_by`, `created_at`.
- **Targets are only ever chosen from catalogue lists**, and the API rejects a target that isn't in
  the catalogue. Catalogue names, not ids, so a catalogue reload can't orphan a mapping; a mapping
  whose target disappears is flagged in the list.
- Applied in `match_decoded` before the model filter: each matching mapping adds its catalogue
  (make, model) to the names the decode may mean, so cross-make works (Geo → Chevrolet).
- **One decode can need several targets.** Mercedes "C-Class" is C 220 / C 230 / C 240 / C 280 /
  C 300 … in the catalogue, split by year and engine (dev catalogue, 2026-10-15). Several mappings
  for one decode each add a name; the existing year filter and engine narrowing pick among them.
  The UI offers multi-select targets for this.
- The existing yard-string rule engine stays for vehicles without a usable decode (~650, 3.6%),
  rebuilt with the same pick-from-list UI: the raw side is the exact yard string from the
  discrepancy group, the target picked from the catalogue. Scope is global or one yard (picked, not
  typed); prefix/regex and priority go.

### 2.3 The fix workflow

Discrepancies page, grouped by **(reason, NHTSA make, model, series)** with year range, vehicle count
and yards:

- **Fixable groups first** (`model_not_in_catalogue`, `make_not_in_catalogue`). Catalogue-gap
  groups sit in their own tab with the catalogue's year coverage shown. No admin action resolves
  them, but they show yard trends (which yards stock which makes and years) and suggest per-yard
  rules, so each gap group breaks down by yard and the tab can be filtered by yard.
- Each fixable group shows the **closest catalogue models for that make in that year range**
  (similarity-ranked) as one-click choices (several can be chosen, see §2.2), plus a search box
  limited to that make's catalogue models. A "different make" toggle opens the make list for
  cross-make cases.
- Choosing a target shows a **preview**: "maps N vehicles; M of them get a match", computed by
  running the matcher with the proposed mapping against the group's vehicles (decodes are cached,
  so no NHTSA calls).
- **Confirm** creates the mapping and requeues exactly the affected vehicles. The worker resolves
  them within seconds and the group leaves the list.
- **Ignore** marks the group ignored. It reopens if new vehicles arrive with a different decode.

**Catalogue gaps resolve themselves** (built 2026-10-16: CronJob `catalogue-gap-recheck`, 03:30 New York,
`pipeline.worker --requeue-reasons`; first prod run requeued 11,516): a nightly job requeues `year_not_in_catalogue` /
`model_year_gap` vehicles. That's ~14k vehicles with cached decodes, so it costs catalogue queries
only.

### 2.4 Vehicle page

Reached from a group or by search (VIN, stock number, yard):

- Shows the yard's fields, the raw NHTSA decode, the candidates and match method, and the
  discrepancy reason.
- **Re-resolve**: requeue this vehicle (clears `car_id_*` and `resolve_attempted_at`).
- **Manual match**: cascading year → make → model → trim → engine pickers over the catalogue; stores
  catalogue car ids (as `apply_manual_override` does today).
- **Re-scrape yard**: the yard scrapers fetch whole inventories (most are one request), so
  "re-scrape this vehicle" is a Run now of that yard's ScrapeJob through scrape-job-manager's run-now
  annotation, then the vehicle re-resolves. The source → ScrapeJob link is an explicit label on each
  ScrapeJob (`gyopart.danwils.com/source: <vehicles.source>`) set in `templates/scrapers.yaml`.
  Names don't map mechanically: `picknpullsa` vs `picknpull-sa`. A true single-vehicle refetch is
  only possible for scrapers with per-vehicle detail endpoints (u-pull-n-save, pull-a-part); out of
  scope for v1.

### 2.5 Mappings page

The table of mappings with affected-vehicle counts, creator and date. Delete requeues the affected
vehicles. Edit is delete + create, so a change always goes through the preview.

### 2.6 Shape of the app

- Same stack as the scrape-job-manager UI: FastAPI JSON API + React SPA in one image, served behind
  Traefik.
- Sign-in through authentik in the app, with access limited to a new authentik group,
  `gyopart-admin` (it writes).
  Public host only once that's in.
- The web process never does bulk work: actions write rows (mappings, requeues, annotations) and the
  worker does the rest.
- All list endpoints paged and filtered in SQL.
- No `create_all`; schema changes go through the Alembic root in `junkyard-inventory-scrapers/`.
- LLM suggester removed.
- Tests: reason classification and mapping application in `car_matcher` (table-driven from real
  decodes), API tests over a fixture catalogue, Playwright for the group → pick → confirm flow.

### 2.7 Discrepancy-fix MCP (phase 7)

An agent works the discrepancy queue the way the UI does, from any MCP client: the user pastes
`https://gyopart-admin.danwils.com/mcp` into the harness, signs in through the browser, and the agent
can start. Same pattern as nodewright and webdoc (`apps/webdoc/api/webdoc/oauth.py`, copied):

- **OAuth**: the admin is the authorization server for its MCP clients (the MCP SDK's
  `mcp.server.auth` routes: metadata, dynamic registration, `/authorize`, `/token`, `/revoke`).
  `/authorize` hands over to a consent page that needs the normal admin session, so who may connect
  is decided by authentik's `gyopart-admin` binding, as for the UI. Tokens are random, stored
  hashed, in four `mcp_oauth_*` tables (migration `0006`); access 1 h, refresh rotated.
- **Scope = the existing fixes, nothing else**: read discrepancies, vehicles, cached decodes and the
  catalogue; preview and create decode mappings and yard rules; ignore/un-ignore a group; delete a
  mapping an agent made. No manual matches, no re-scrapes, no deleting the user's own mappings.
  Every write goes through the same functions as the API, so targets must exist in the catalogue and
  the affected vehicles are requeued the same way. `created_by` reads `agent:<client> (<user>)`.
- **Queries**: an overview (counts by tab, reason and yard), groups in priority order (most open
  vehicles first, filterable by tab/yard/make/text), a group's detail (years, yards, catalogue
  coverage, suggestions, existing mappings), the vehicles in a group (filter by year/yard, optional
  decodes), one vehicle (by id, VIN or stock number) with its decode, one cached decode by VIN, and
  catalogue lookups down to car records (year, make, model, trim, engine).
- Decodes come back with the empty NHTSA fields dropped (most of the ~140 are empty).
- **Disconnect**: an Agents list in the SPA shows connected clients and revokes them.

## 3. Phases

1. **Worker** — built 2026-10-15 (gyopart 23296ba), running in dev, not yet in prod. Reason +
   decode columns, discrepancy cleanup on match, `decode_mappings` applied in `match_decoded`,
   migration `0005` (in `junkyard-platform/db/`; nothing applies migrations automatically). The
   worker and admin images install `junkyard_common` from source, so no PyPI release is needed for
   them; the scrapers pin 0.1.0 and don't touch these tables.
   Dev after the backfill (2026-10-15): year_not_in_catalogue 13,561 · model_year_gap 3,116 ·
   make_not_in_catalogue 3,037 · model_not_in_catalogue 2,909 (136 distinct make/model pairs) ·
   no_vin 510 · decode_failed 232. A test mapping (Chevrolet Silverado HD / series 2500 → Silverado
   2500 HD) matched 66 of 126 vehicles; the other 60 are 2024–2026, beyond the catalogue's
   2019–2023, and were re-classified accordingly.
2. **API + SPA discrepancy workflow** (§2.3) and mappings page (§2.5), LAN-only — built 2026-10-15, running
   in dev at `http://admin.gyopart-dev.local` (old pages still at `/admin/ui`). Six workflows verified against
   the dev data (`admin_ui/.ui_dev_state.md`); dev has the C-Class mappings (458 cars matched).
   Finding for phase 1: NHTSA series like "1500 (1/2 Ton)" never form the catalogue's "Suburban 1500" /
   "Silverado 1500", so big Chevrolet/GMC groups read as gaps; stripping the bracketed part in
   `decoded_model_keys` would likely fix them without mappings (proposed, not done).
3. **Vehicle page** (§2.4) — built 2026-10-15, in dev. Search (VIN / stock / id), match state with
   candidates as catalogue cars, re-match, manual match (year → make → model → car), and yard re-scrape
   via the ScrapeJob's run-now annotation (admin-api ServiceAccount: get/list/patch scrapejobs in its own
   namespace; job found by label `gyopart.danwils.com/source`, else source with _ → -). Verified with a
   real parts-galore run in dev. Admin image runs Python 3.12 (microk8s CA vs 3.13's strict X.509).
   Series fix from phase 2's finding landed with it: ~810 more dev vehicles matched (Silverado 1500 all
   729, Avalanche 182, Suburban 1500 408/486 — the rest are 1997/1999, catalogued as C1500/K1500).
4. **authentik + public host** — built 2026-10-15, on in dev at https://gyopart-admin-dev.danwils.com (prod will
   be gyopart-admin.danwils.com: one level under danwils.com, which Cloudflare's free certificate covers).
   authentik app `gyopart-admin`, access = group `gyopart-admin`; one client for both environments.
   `admin_api/auth` (ported from the sjm UI with its fixes) guards the SPA, `/api` and the old pages: page
   loads → sign-in and back, API → 401, writes need `X-Admin` / `HX-Request`, LAN host → public host.
   Mappings and rules record the signed-in user.
5. **Cleanup** — done 2026-10-15 (dev): old Jinja pages and their routes, the old rule UI, the LLM suggester
   (+ its cron job) and `create_all` removed; the rule engine stays for yard rules (§4). `/admin/...` URLs
   redirect to the SPA; probes are HTTP on `/api/config`; the app starts with a database down.
6. **Prod** — promoted 2026-10-15 (gyopart main 48c4d38): https://gyopart-admin.danwils.com, prod DB at 0005, images
   admin-api sha-6b4201f65922 / vin-resolver sha-2af88a943620. No mappings carried over (prod starts fresh). Re-match
   of every unmatched vehicle: 102,941 → 104,055 matched (+1,114, from the bracketed-series fix alone); open reasons:
   year_not_in_catalogue 9,779 · model_not_in_catalogue 2,408 · make_not_in_catalogue 2,317 · model_year_gap 1,737 ·
   no_vin 512 · decode_failed 206.
7. **Discrepancy-fix MCP** (§2.7; user, 2026-10-15/16) — instead of LLM suggestions, an MCP server at `/mcp` scoped
   to the existing fixes, with OAuth sign-in like nodewright and webdoc. Built 2026-10-16 (gyopart 59f05d4), on in dev at
   https://gyopart-admin-dev.danwils.com/mcp: dev DB at 0006, admin-api sha-59f05d45036c; every tool verified against
   the dev data (a create → re-match → delete round trip included); the user connected Claude Code through the browser
   sign-in and created the E-Class mapping with it (157 cars matched, 28 exact, the rest Base vs 4Matic® within one model).
   Prod: https://gyopart-admin.danwils.com/mcp, prod DB at 0006, admin-api sha-59f05d45036c (2026-10-16). Later (user): a
   richer VIN mapper (trim/engine-level mappings), which will lean on this: designed 2026-10-27 in [matching-v2-design.md](matching-v2-design.md), with the GPU fix-suggestion agent.

## 4. Decisions (user, 2026-10-15)

- **Yard-string rules stay** for vehicles without a usable decode (cheap to keep), rebuilt with the
  pick-from-list UI (§2.2).
- **Cross-make mappings are allowed** (Geo Prizm → Chevrolet Prizm, Geo Metro → Chevrolet Metro).
- **Catalogue-gap groups stay visible**, broken down by yard: they show yard trends and suggest
  per-yard rules (§2.3).
- **Access: a new authentik group, `gyopart-admin`** (§2.6).
