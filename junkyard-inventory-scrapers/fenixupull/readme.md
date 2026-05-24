# Fenix U-Pull — Inventory Scraping Strategy

**VIN is available** — full 17-character VIN is present in every inventory row.

---

## Locations

| Location | Slug | Taxonomy ID | Address | Phone | Email |
|---|---|---|---|---|---|
| Elmira, NY | `elmira-ny` | 54 | 1592 Sears Road, Elmira, NY 14903 | (607) 739-3851 | info@fenixupull.com |
| Binghamton, NY | `binghamton-ny` | 55 | 230 Colesville Rd, Binghamton, NY 13904 | (607) 775-1900 | info@fenixupull.com |
| East Syracuse, NY | `east-syracuse-ny` | 56 | 7030 Myers Road, East Syracuse, NY 13057 | (315) 656-7533 | info@fenixupull.com |
| Moultrie, GA | `moultrie-ga` | 57 | 232 Industrial Road, Moultrie, GA 31768 | (229) 985-1052 | info@fenixupull.com |

All locations: **Mon–Sun 9:00 a.m. – 6:00 p.m.** (doors close at 5:30 p.m.)

> **Note:** A fifth location, Belleville, MI (`belleville-mi`, ID: 58, ~895 vehicles), exists in the taxonomy but is temporarily disabled in the UI. The site's JS detects `fnx_location=5` and resets the cookie. The slug can be tried in inventory queries but the location is no longer actively shown to users.

---

## Platform

Custom WordPress theme (`fenixupull`) with a custom inventory CPT backed by an `inventory_location` taxonomy. Inventory search results are **fully server-side rendered (SSR)** — no JavaScript execution required.

**Key identifiers:**
- Custom theme path: `/wp-content/themes/fenixupull/`
- DataTables CDN loaded (`cdn.datatables.net`) for client-side sorting/filtering only — not used for AJAX data fetching
- Custom REST endpoint: `/wp-json/api/getModels?make={MAKE}`
- WP taxonomy: `/wp-json/wp/v2/inventory_location`
- No CSRF token, no nonce, no session cookie required for any scraping endpoint

---

## Inventory Data Fields

Every table row contains:

| Column | Notes |
|---|---|
| Make | e.g. `HONDA` |
| Model | e.g. `CIVIC` |
| Year | 4-digit |
| Row | Yard row number |
| VIN | Full 17-character VIN ✓ |
| Stock Number | Internal ID, e.g. `204013137` |
| Date Placed In Yard | `MM/DD/YY` format |
| Location | Plain-text location name, e.g. `Elmira, NY` |
| Images | Thumbnail link to detail page |

---

## API / Endpoints

### 1. Get Makes

Makes are hardcoded in the search form HTML. As of May 2026, the full list is:

```
ACURA, AUDI, BMW, BUICK, CADILLAC, CHEVROLET, CHRYSLER, DODGE, FIAT, FORD,
FREIGHTLINER, GMC, HONDA, HUMMER, HYUNDAI, INFINITI, ISUZU, JAGUAR, JEEP, KIA,
LAND ROVER, LEXUS, LINCOLN, MAZDA, MERCEDES-BENZ, MERCURY, MINI, MITSUBISHI,
NISSAN, OLDSMOBILE, PONTIAC, RAM, SAAB, SATURN, SCION, SUBARU, SUZUKI, TOYOTA,
TRIUMPH, VOLKSWAGEN, VOLVO
```

To scrape dynamically, parse `<select id="js-input-make"> <option value="{MAKE}">` from the inventory page HTML.

### 2. Get Models for a Make

```
GET /wp-json/api/getModels?make={MAKE}
```

Returns a JSON array of model strings. No authentication. No cookie required.

**Example:**
```
GET /wp-json/api/getModels?make=HONDA
→ ["ACCORD","CIVIC","CR-V","CROSSTOUR","ELEMENT","FIT","ODYSSEY","PASSPORT","PILOT","PRELUDE","RIDGELINE"]
```

### 3. Search Inventory

```
GET /inventory/?location={location-slug}&make={MAKE}&model={MODEL}
```

- Returns full SSR HTML page with a `<table>` containing inventory rows.
- `location` accepts a **single slug** or **comma-separated slugs** (e.g. `elmira-ny,binghamton-ny`).
- **Server hard-cap: 50 rows per response regardless of filter.** See Pagination section below.
- No cookie required — location is controlled entirely by the `location` URL parameter.
- `model` is optional; omitting it returns all models for the given make (still capped at 50).

**Parse target:** `table > tbody > tr` — each row has 10 `td` cells in column order above.

### 4. Vehicle Detail Page

```
GET /inventory/{STOCK_NUMBER}/
```

Returns individual vehicle page with: Location, Row, VIN, Stock Number, Date Placed In Yard, Engine Size (if available), Trim (if available), yard address, and photo gallery.

**Image URL pattern:**
```
https://fenixupull.com/wp-content/uploads/{YYYY}/{MM}/{STOCK}_1-150x100.jpg   # thumbnail
https://fenixupull.com/wp-content/uploads/{YYYY}/{MM}/{STOCK}_1.jpg            # full size
```

Where `{YYYY}/{MM}` matches the month the vehicle was placed in the yard.

### 5. Recent Inventory

```
GET /recent-inventory/
```

Returns 50 most recently added vehicles as an SSR HTML table (same column structure as search results). **Location is determined by the `fnx_location` session cookie**, not a URL param — this endpoint does not accept a location query string. To use for incremental runs, query it once per location by setting the cookie.

---

## Full Inventory Strategy

The server caps results at 50 rows per request. To collect complete inventory:

### Step 1 — Enumerate makes and models

```python
# Scrape makes from form HTML (or use the hardcoded list above)
makes = scrape_makes_from_form()

# For each make, fetch its models
for make in makes:
    models = requests.get(f"https://fenixupull.com/wp-json/api/getModels?make={make}").json()
```

### Step 2 — Query each location × make × model

**Critical:** Query **one location at a time**. Multi-location queries (`location=loc1,loc2,...`) combine results from all locations before applying the 50-row cap — you will lose data for popular make/model combos. Single-location queries ensure per-location counts stay well under 50.

```python
LOCATIONS = ["elmira-ny", "binghamton-ny", "east-syracuse-ny", "moultrie-ga"]

for location in LOCATIONS:
    for make in makes:
        for model in models_for_make[make]:
            url = f"https://fenixupull.com/inventory/?location={location}&make={make}&model={model}"
            html = requests.get(url).text
            rows = parse_table(html)  # parse tbody > tr
            # persist rows keyed by (vin, stock_number)
```

### Step 3 — Parse table rows

Each `<tr>` in `<tbody>` has exactly 10 `<td>` cells:
```
[0] Make
[1] Model
[2] Year
[3] Row
[4] VIN
[5] Stock Number
[6] Date Placed In Yard
[7] Location
[8] Images (contains thumbnail <a href="/inventory/{STOCK}/">)
[9] "More Info" button (link to /inventory/{STOCK}/)
```

### Approximate request volume

With ~41 makes × avg ~7 models each × 4 locations = **~1,150 requests** per full run. At 1 req/sec this completes in under 20 minutes.

---

## Incremental / Recent-Arrivals Runs

The `/recent-inventory/` page shows the 50 most recently added vehicles (ordered by Date Placed In Yard descending). It is cookie-based, so:

1. Set `fnx_location={id}` cookie (Elmira=1, Binghamton=2, East Syracuse=3, Moultrie=4) before each fetch.
2. Fetch `GET /recent-inventory/` and parse the table.
3. Compare stock numbers / VINs against the stored inventory.
4. If any stock number in the recent list is already in the DB, all older entries are also known — stop here and skip the full run for this location.
5. If all 50 are new, a full re-run for that location is warranted.

> **Caveat:** The 50-row cap on recent inventory means a yard adding more than 50 vehicles between runs will require a full re-run to avoid gaps. Fenix yards add 10–30 vehicles per day so daily runs should be safe.

---

## Notes

- No authentication or nonce required for any scraping endpoint.
- `fnx_location` cookie is used by the site's JS to pre-select location in the nav — **not required** for inventory scraping; use the `location` URL param instead.
- DataTables is loaded from CDN and used purely for client-side sort/filter on the already-rendered 50-row result; it never fires AJAX requests for more data.
- Stock number prefix appears to encode location: `204xxxxx` = Elmira, `203xxxxx` = Binghamton, `213xxxxx` = East Syracuse, `306xxxxx` = Moultrie — but this is not guaranteed and should not be relied upon; use the `Location` column instead.
- The `/wp-json/api/inventory-image-sync` endpoint exists but appears to be an admin-only image sync utility — not useful for scraping.
- Belleville, MI was an active Fenix location that is now hidden. Its data may still be queryable at `location=belleville-mi` but was not tested.
