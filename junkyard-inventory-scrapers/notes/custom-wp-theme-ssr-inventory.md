# Custom WordPress Theme — SSR Inventory Pattern

**Applies to:** fenixupull.com (confirmed), centralfloridapickandpay.com (confirmed — simpler variant, see below), baughmansupullit.com (confirmed — enumerate-by-make variant, see below), budgetupullit.com (confirmed — enumerate-by-make, VINs available, WP theme `car-repair-services`)

---

## Identification

- Custom WordPress theme (`/wp-content/themes/fenixupull/`) with no standard WP inventory plugin
- DataTables CDN loaded (`cdn.datatables.net`) but used only for client-side sort/filter — **not** for AJAX pagination
- Inventory data fully server-side rendered — just a GET request with URL params
- Custom REST endpoint: `/wp-json/api/getModels?make={MAKE}`
- Custom taxonomy `inventory_location` accessible via `/wp-json/wp/v2/inventory_location`
- VIN in every row

## Key Findings

- **No auth, no nonce, no CSRF token required** for any scraping endpoint
- **Server hard-cap: 50 rows per response** — applies to all inventory search requests regardless of filter breadth
- Multi-location queries (`location=loc1,loc2,...`) hit the cap on combined results — always query one location at a time
- Makes are hardcoded in the form HTML; models loaded via public REST endpoint per make
- Full inventory requires: 4 locations × ~41 makes × avg ~7 models = ~1,150 GET requests
- Recent arrivals at `/recent-inventory/` uses `fnx_location` cookie to select location — not a URL param; set cookie before each fetch
- Stock number prefix encodes location (204=Elmira, 203=Binghamton, 213=East Syracuse, 306=Moultrie) but not reliable — use the Location column

## How to Find the Inventory API Fast

1. Load `/inventory/` with a location cookie set, inspect the form HTML for the action URL
2. Look for `<select id="js-input-make">` to enumerate makes
3. Check network on make selection — XHR to `/wp-json/api/getModels?make={MAKE}` reveals models endpoint
4. Submit the form and observe URL — GET params `location`, `make`, `model` are the full API
5. Check page source for inline `<script>` tags with `DataTable` — if no AJAX config present, it's client-side only

## Cookie vs URL Param

The `fnx_location` cookie is used for navigation UI only. For inventory queries, use the `location` URL parameter — it overrides the cookie for the server-side render.

---

## Simpler Variant — Full Inventory in One SSR Table (centralfloridapickandpay.com, coloradoautoandparts.com)

Some WP sites with a custom inventory plugin render the **entire inventory** (~1,000+ rows) into a single `<table>` on one page, with no row cap or make/model filtering needed server-side. DataTables paginates them client-side only.

- `$('#vehicles').dataTable({...})` with **no `ajax:` key** = all data already in the DOM
- Confirm with `$('#vehicles').DataTable().rows().count()` in browser console — if count >> visible rows (10), DataTables is paginating in-memory
- Single `requests.get('/vehicle-inventory/')` returns everything; no looping over makes/models
- Identify this pattern fast: check DataTables init JS for absence of `ajax:` or `serverSide: true`
- This variant also appears on **non-WP plain PHP sites** (jacksusedautoparts.com confirmed): the main page embeds an `<iframe src="/vehicleInventory.php">` — fetch the iframe URL directly, same strategy
- The PHP page may prepend a plain-text `Updated: {datetime}` line before the HTML — reliable cache-busting signal, compare before parsing
- **coloradoautoandparts.com variant:** no custom inventory plugin at all — table is embedded directly in a Colibri Page Builder WP page. No VIN. Hidden columns (Row, Arrival Date) are present in HTML source even though `display:none` in browser. Skip `.child` rows (DataTables responsive duplicates). The `Updated:` text node precedes the table as a raw text node, not inside a labelled element.

---

## Enumerate-by-Make Variant — No Model REST Endpoint (baughmansupullit.com)

Some WP SSR inventory sites skip the model REST endpoint entirely and pre-load **all models for all makes** in a single flat dropdown. The scraping loop is simpler:

- No `wp-json/api/getModels` call needed — models list is already in the form HTML
- Query by make only: `GET /inventory/?make={MAKE}&model=` — returns all vehicles for that make with no row cap
- All makes are hardcoded in `<select id="makeSelect">` — 37 makes on baughmansupullit
- **No pagination** — complete per-make results in one response
- Colibri Page Builder Pro + Formidable Forms renders the GET form (not a custom theme or plugin)
- `<td data-label="Yard Date">` + `<td style="font-size: 0px;">STK######` pattern for date and stock number
- Stock number is the unique vehicle key — **no VIN available**
