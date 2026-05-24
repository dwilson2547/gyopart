Build scrapers for each VIN-present yard using `junkyard_common` for all DB writes. See the
implemented scrapers below as reference, then work through the checklist.

> Use `JUNKYARD_DATABASE_URL` env var (via `junkyard_common.db.get_engine()`). Every scraper
> writes `Location`, `Vehicle`, and `ScrapeRun` rows. Use `WebCacheClient` + `RequestAuthClient`
> (from `scrape_stack`) for rate limiting and request caching. See `notes/` for platform-specific
> patterns that reuse across sites.

---

## Reference Implementations

Fully built scrapers using `junkyard_common` — use these as templates:

| Scraper | Strategy | Locations | Dedup key | Notes |
|---------|----------|-----------|-----------|-------|
| `pull_a_part_scraper/` | ajax-api (JSON) | multi | `{ticket_id}:{line_id}` | phases: locations → makes → inventory → details; detail fetch populates trim/engine/etc |
| `pic-n-pull/` | ajax-api (JSON) | multi | `vehicle.id` | location-scoped zip search; VIN optionally present |
| `parts-galore/` | static-html | 1 | VIN | single GET, BeautifulSoup table parse, pg upsert |
| `ryans_pic_a_part/` | Playwright intercept | 1 | ES `_id` | intercepts autorecycler.io elasticsearch msearch; VIN via `vin_text` field |

---

## Checklist — VIN-Present Sites

Check off each scraper when complete. Each entry has the `SOURCE` constant to use, the strategy,
and the key implementation details from the recon README. Dedup key is `vin` as `source_key`
unless noted otherwise.

---

### Group 1: URG IIS Pro v2 — SSR Make/Model Crawl

These sites share the same WordPress + URG IIS Pro v2 platform (`iis-pro-v2` plugin). See
`notes/urg-iis-pro-v2-platform.md` for shared patterns. Full crawl: GET `/parts/makes/` →
GET `/parts/{MAKE}/` → GET `/parts/{MAKE}/{MODEL}/` → parse `.card-price` divs. VIN in
`<b>Vin :</b>` text. Stock number is the card `id` attribute. Dedup on `vin` (use as
`source_key`). No auth, no nonce needed.

- [x] **`speedwayap`** — `SOURCE = "speedway_ap"` · `speedwayap/`
  - 1 location: Chicago/Joliet IL
  - Same SSR make/model crawl as below; single `urgid`
  - `preview_image_url` from CDN: `da8h1v3w8q6n5.cloudfront.net/{urgid}/images/{STOCK}/...`
  - README: `speedwayap/readme.md`

- [x] **`arizonaautoparts`** — `SOURCE = "arizona_auto_parts"` · `arizonaautoparts/`
  - 2 locations (Phoenix, Tucson) — single unified inventory (`urgid = 'AZ03'`)
  - Location inferred from stock suffix: `A`=Phoenix, `B`=Tucson, `U`=unknown
  - Seed both Location rows; set `source_location_id` to stock suffix
  - `mileage` maps to `Vehicle.extras["miles"]` or `extras`
  - Recent arrivals: `/latest-arrivals/` (60 most recent with `Arrive Date`)
  - README: `arizonaautoparts/readme.md`

- [x] **`las_parts`** — `SOURCE = "las_parts"` · `las-parts/`
  - 3 yard IDs: `NJ12`, `NJ29`, `II08` — 2 confirmed locations (Ringoes NJ, Port Murray NJ)
  - Location from CDN image path prefix: `cloudfront.net/{yard_id}/images/`
  - `II08` has unknown address — store what's known, flag `address=None`
  - Recent arrivals: `/latest-arrivals/` — same stop-on-known-VIN strategy
  - README: `las-parts/readme.md`

- [x] **`strickerautoparts`** — `SOURCE = "stricker_auto_parts"` · `strickerautoparts/`
  - 1 location: single full-service recycler (not U-Pull)
  - Same URG SSR crawl pattern; `iisajax` endpoint present but not needed
  - README: `strickerautoparts/readme.md`

- [x] **`midwayupull`** — `SOURCE = "midway_upull"` · `midwayupull/`
  - 2 active locations: Liberty MO (`MO09`), Kansas City KS (`MO38`) — Tulsa not online
  - Platform variant: JS prefix is `iisupull` not `iis` — minor difference
  - Uses `admin-ajax.php` POST (not pure SSR GET) — check `notes/urg-iis-pro-v2-platform.md`
  - Fields per card: Stock#, Year, Make/Model, VIN, Location, Row, Set Date
  - README: `midwayupull/readme.md`

---

### Group 2: Simple SSR Tables

Single GET (or enumerate by make) — no AJAX, no auth. Parse `<table id="vehicles">` with
BeautifulSoup. Pattern documented in `notes/custom-wp-theme-ssr-inventory.md`.

- [x] **`central_florida_pick_and_pay`** — `SOURCE = "central_florida_pick_and_pay"` · `centralfloridapickandpay/`
  - 1 location: Orlando FL — 10694 Cosmonaut Blvd, 407-783-7985
  - **1 GET request** for all ~1,275 vehicles — entire inventory in `<table id="vehicles">`
  - Columns (0-indexed): Year, Make, Model, Color, Engine, Row, Arrival Date (`MM/DD/YY`), VIN
  - `Vehicle.extras["engine"]` for the engine field (no direct schema column maps cleanly)
  - Table sorted arrival-date desc — parse top-down for incremental runs
  - README: `centralfloridapickandpay/readme.md`

- [x] **`picknpullsa`** — `SOURCE = "picknpullsa"` · `picknpullsa/`
  - 1 location: San Antonio TX — independent yard, NOT a Pull-A-Part affiliate
  - **1 GET request** — same `<table id="vehicles">` pattern
  - Columns: Year, Make, Model, Color, VIN, Engine, Row, Arrival Date
  - Pre-1981 vehicles may have short manufacturer serial instead of 17-char VIN — store as-is
  - README: `picknpullsa/readme.md`

- [x] **`budget_upullit`** — `SOURCE = "budget_upullit"` · `budgetupullit/`
  - 1 location: Winter Garden FL — 881 S 9th St, 407-656-4707
  - Enumerate by make (39 makes): `GET /current-inventory/?make={MAKE}&model=`
  - Returns `<table class="resultsTable">` — pick the **last** `.resultsTable` on the page
  - Columns: Year, Make, Model, Stock# (`STK#####`), Row, VIN (`<td data-label="\nVin">`), Date (`MM.DD.YY`)
  - `source_key = vin` since VIN is present; `stock_number` → `extras["stock_number"]`
  - Recent arrivals: `/new-arrivals/` — VIN present, same stop-on-known-VIN strategy
  - README: `budgetupullit/readme.md`

---

### Group 3: CSV / XML Feeds

No HTML parsing needed — structured data directly.

- [x] **`ipullupull`** — `SOURCE = "ipullupull"` · `ipullupull/`
  - 4 locations: Fresno, Pomona, Sacramento, Stockton CA
  - **4 CSV downloads** (one per yard): `https://ipullupull.com/{yard}.csv`
  - CSV columns: `Date Added, Year, Make, Model, VIN, Stock#, Yard, Row, Fresh Set`
  - Strip leading spaces from all header keys (`str.strip()`)
  - `source_key = vin`; `extras["stock_number"]`, `extras["fresh_set"]`
  - `Fresh Set == "Yes"` marks newest batch — use for incremental check
  - Location slugs: `fresno`, `pomona`, `sacramento`, `stockton`; `source_location_id` = slug
  - README: `ipullupull/readme.md`

- [x] **`utpap`** — `SOURCE = "utpap"` · `utpap/`
  - 2 locations: Orem UT (~674 vehicles), Ogden UT (~974 vehicles)
  - **Unauthenticated config leak** → GET `/api/admin/yard-config/utah_pic_a_part` on the Cloud Run
    host returns JSON with `inventory_file.inventory_url` — the raw CrushYMS XML feed URL
  - XML: `<INVENTORY>` root, `<ASSET>` children. Key tags: `STOCKNUMBER` (dedup key if no VIN),
    `VIN`, `iYEAR`, `MAKE`, `MODEL`, `COLOR`, `MILEAGE`, `YARD_IN_DATE`, `VEHICLE_ROW`
  - `source_key = VIN`; `extras["stock_number"]` = `STOCKNUMBER`
  - See `notes/crushyms-xml-feed-via-saas-config-leak.md` for feed URL pattern
  - README: `utpap/readme.md`

---

### Group 4: REST / JSON APIs

Clean JSON responses — no HTML parsing.

- [x] **`wrenchapart`** — `SOURCE = "wrenchapart"` · `wrenchapart/`
  - 11+ locations across multiple states — fetch from `GET https://api.wrenchapart.com/locations`
  - **Single GET** `/v1/vehicles` returns full ~11K inventory as flat JSON array — no pagination
  - VIN always present. GPS row coordinates (lat/lon) per vehicle — store in `extras`
  - `locationId` / `yardId` params available for per-location filtering
  - Incremental: `GET /v1/vehicles?days=N` where N = days since last run
  - `source_key = vin`
  - README: `wrenchapart/readme.md`

- [x] **`u_pull_n_save`** — `SOURCE = "u_pull_n_save"` · `u-pull-n-save/`
  - Multiple locations — discover via stores endpoint
  - REST API: `GET /api/vehicles/search/?store={storeId}&year={year}&make={make}&model={model}`
  - Full detail (including VIN) via `GET /api/vehicles/{vehicleID}`
  - `source_key = vin` (present in detail response)
  - README: `u-pull-n-save/readme.md`

---

### Group 5: WordPress admin-ajax

These sites use `wp-admin/admin-ajax.php` with custom actions. Nonce handling varies — see each README.

- [x] **`fenixupull`** — `SOURCE = "fenix_upull"` · `fenixupull/`
  - 4 locations: Elmira NY, Binghamton NY, East Syracuse NY, Moultrie GA
  - **50-row server cap** — must query each `location × make × model` separately
  - No nonce needed; no cookie needed for inventory (use `location` URL param, not cookie)
  - Endpoint: `GET /inventory/?location={slug}&make={MAKE}&model={MODEL}`
  - Models per make: `GET /wp-json/api/getModels?make={MAKE}`
  - ~1,150 requests for full crawl; columns: Make, Model, Year, Row, VIN, Stock#, Date, Location
  - `source_key = vin`; `extras["stock_number"]`
  - Recent: `GET /recent-inventory/` with `fnx_location={id}` cookie (per location)
  - README: `fenixupull/readme.md`

- [x] **`tearapart`** — `SOURCE = "tear_a_part"` · `tearapart/`
  - Multiple locations — extract from locations endpoint (see README)
  - Nonce required: extract `sif_ajax_nonce` from inline `<script>` on `GET /inventory/`
  - Nonce valid ~12 hours; refresh once per run
  - Action: POST `admin-ajax.php` with `action=sif_search_inventory&nonce={nonce}&...`
  - VIN in every record from primary endpoint
  - `source_key = vin`
  - README: `tearapart/readme.md`

- [x] **`pull_n_save`** — `SOURCE = "pull_n_save"` · `pull-n-save/`
  - 8 locations: Salt Lake City, Phoenix S/N, Glendale, Gilbert UT, Springville UT, Tucson, Riverside CA
  - Use **legacy** `getVehicles` action (no nonce needed; newer `pns_get_inventory_assets` is WAF-blocked without browser session)
  - Locations: POST `action=getStores` → JSON array of `{StoreNumber, StoreName, State}`
  - `source_key = vin`
  - README: `pull-n-save/readme.md`

- [x] **`wegotused`** — `SOURCE = "wegotused"` · `wegotused/`
  - Multiple locations — REST-like GET endpoints via `inventory-7lt` WP plugin
  - No nonce, no auth required — plain GET throughout
  - Paginated: `GET /inv?inv[sort][yard_date]=0&inv[page]=N` (sort newest-first)
  - Stop when a VIN already in DB is encountered (incremental strategy)
  - VIN present in every row
  - `source_key = vin`
  - README: `wegotused/readme.md`

---

### Group 6: Special / Complex

- [x] **`chesterfieldauto`** — `SOURCE = "chesterfield_auto"` · `chesterfieldauto/`
  - 3 locations: Richmond VA, Fort Lee VA, Southside VA — all appear in every search response
  - **ASP.NET Core MVC** — must POST by make; GET returns empty table
  - Token: extract `__RequestVerificationToken` once per session from `GET /search-our-inventory-by-location`
  - Token is session-scoped (not per-page) — one GET sufficient per run
  - POST: `action=/search-our-inventory-by-location?SelectedMake.Id={makeId}` with form body
  - VIN in `<button data-target="#MAKE{VIN}">` — extract trailing 17 chars via regex
  - `Store` column identifies location: "Richmond", "Fort Lee", "Southside"
  - `source_key = vin`; `extras["stock_number"]`, `extras["transmission"]`, `extras["drive"]`
  - Recent: `GET /newest-cars` — plain GET, no token needed, ~120 vehicles
  - README: `chesterfieldauto/readme.md`

- [x] **`pyp`** — `SOURCE = "pyp"` · `pyp/`
  - **62 locations** — LKQ Corporation subsidiary; all on same domain
  - WP SSR paginated by location; VIN in `<b>VIN: </b>` field on each card
  - `source_key = vin`; `stock_id` format: `{locationCode}-{stockNo}` → `extras["stock_id"]`
  - Newest-first pagination — compare page 1 `Available` date for incremental cutoff
  - README: `pyp/readme.md`

- [x] **`usedautopartsfl`** — `SOURCE = "used_auto_parts_fl"` · `usedautopartsfl/`
  - 1 location — single yard
  - Data source: Google Sheets CSV export + AppSheet API
  - VIN column: `VIN #`; coverage ~96% (957/999 rows) — skip/log rows without VIN
  - `source_key = vin` where present; fall back to `extras["stock_number"]` for no-VIN rows
  - README: `usedautopartsfl/readme.md`

---

## Sites Excluded (No VIN)

Not on the checklist — skip until VIN becomes available or a composite-key approach is prioritized.

| Site | Reason |
|------|--------|
| `baughmansupullit` | Stock number only (`STK######`) |
| `coloradoautoandparts` | No identifier at all |
| `indyupullit` | Internal stock number (~40% missing) |
| `jacksusedautoparts` | Zero VIN data |
| `jksalvageco` | WP Car Manager — VIN not stored anywhere |
| `sturtevantauto` | No VIN; `REFERENCE` col is engine spec |
| `us_auto_parts_sterling_heights` | No VIN (already has a partial scraper) |
| `mcdonoughautoparts` | Car-Part.com platform — not feasibly scrapable |
