# Midway U Pull — Scrape Strategy

## Locations

| Name | URG ID | Address | Phone |
|------|--------|---------|-------|
| Liberty U-Pull | `MO09` | 1101 Old State Hwy 210, Liberty, MO 64068 | 816-781-4886 |
| Muncie U-Pull | `MO38` | 6345 Kansas Ave, Kansas City, KS 66111 | 913-287-6185 |
| Tulsa (no inventory) | *(none)* | 13802 E Apache St, Tulsa, OK 74116 | 918-234-4444 |

> **Note**: The Tulsa location is listed on the contact page but has **no URG yard ID and does not appear in the inventory search dropdown**. Its inventory is not accessible via the online system. Only Liberty (MO09) and Muncie (MO38) have online inventory.
>
> The "Muncie" location name is misleading — it is physically in Kansas City, KS, not Muncie, IN. Likely a historical brand name.

---

## Platform

URG `iis-pro-upull` WordPress plugin v1.6.6. Same URG network as `iis-pro-v2` sites but the **U-Pull variant** — see notes `urg-iis-pro-v2-platform.md` for shared context, with these differences:

- Plugin path: `/wp-content/plugins/iis-pro-upull/`
- JS config variable prefix: `iisupull` (not `iis`), e.g. `iisupullurgid`, `iisupullajax`
- AJAX action names differ: `getMakesIISupull`, `getAllModelsIISupull`, etc. (suffix `IISupull` not `IIS`)
- Inventory URL: `/inventory/{MAKE}/{MODEL}/` (configured via `iisupullpartdir = 'inventory'`)

Yard IDs: `iisupullurgid = 'MO09,MO38'` (comma-separated, both embedded in page source)

---

## VIN Availability

**VINs are present on every vehicle card.** Each record exposes: Stock#, Year, Make/Model, VIN, Location name, Row, Set Date.

---

## Scrape Strategy

### Step 1 — Enumerate Makes

The full make list is embedded as `<option>` values in the page HTML at `/search-inventory/`. No AJAX call needed. Alternatively, `getMakesIISupull` (AJAX) filters by year; use the HTML source for the complete cross-year list.

**Full make list** (59 makes, from HTML):
ACURA, ALFA ROMEO, AMC, AUDI, AUSTIN-HEALEY, BMW, BUICK, CADILLAC, CHEVROLET, CHRYSLER, DAEWOO, DAIHATSU, DODGE, EAGLE, FIAT, FORD, FREIGHTLINER, GEO, GMC, HONDA, HUMMER, HYUNDAI, INFINITI, INTERNATIONAL, ISUZU, JAGUAR, JEEP, KIA, LAND ROVER, LEXUS, LINCOLN, MAZDA, MERCEDES-BENZ, MERCURY, MG, MINI, MITSUBISHI, NISSAN, OLDSMOBILE, OPEL, PETERBILT, PEUGEOT, PLYMOUTH, PONTIAC, PORSCHE, RAM, RENAULT, SAAB, SATURN, SCION, SMART, STERLING, SUBARU, SUZUKI, TESLA, TOYOTA, TRIUMPH, VOLKSWAGEN, VOLVO

### Step 2 — Enumerate Models per Make

For each make, POST to the AJAX endpoint — no nonce, no auth required:

```
POST https://midwayupull.com/wp-admin/admin-ajax.php
Content-Type: application/x-www-form-urlencoded

action=getAllModelsIISupull&make={MAKE_VALUE}
```

Response (JSON):
```json
{
  "error": "false",
  "models": [
    {"model": "DISPLAY NAME", "value": "URL_SLUG"}
  ]
}
```

> The `value` field is the URL-safe slug (spaces → `_`, `/` → `.`, `-` → `~`).

### Step 3 — Fetch Inventory (SSR, no JS required)

```
GET https://midwayupull.com/inventory/{MAKE}/{MODEL}/
```

- Returns **all vehicles** for that make/model, both locations, in a single response
- **No pagination** — all results on one page
- **No auth, no nonce, no cookies required**
- Response is server-side rendered HTML

To filter by one location, append `?id={URGID}`:
```
GET https://midwayupull.com/inventory/CHEVROLET/SILVERADO_1500/?id=MO09
```

### Step 4 — Parse Vehicle Cards

Each vehicle is in a `.car-details-uPull` div. Fields:

```
Stock: {stock_number}
Year: {year}
Make/Model: {make} {model_full}
Vin: {vin}
Location: {Liberty U-Pull | Muncie U-Pull}
Row: {row_code}
Set Date: {YYYY-MM-DD}
```

Example extraction (Python/BeautifulSoup):
```python
for card in soup.select('.car-details-uPull'):
    text = card.get_text('\n')
    # Parse each labeled field from the text block
    stock = re.search(r'Stock:\s*(\S+)', text).group(1)
    vin   = re.search(r'Vin\s*:\s*([A-HJ-NPR-Z0-9]{17})', text, re.I).group(1)
    ...
```

Vehicle image URL (CloudFront CDN):
```
https://da8h1v3w8q6n5.cloudfront.net/mo06/images/{STOCK}/{STOCK}_0.jpg
```

---

## AJAX Actions (all auth-free)

| Action | Params | Returns |
|--------|--------|---------|
| `getYearsIISupull` | *(none)* | `{years: [...]}` — full year range |
| `getMakesIISupull` | `year` | `{makes: [{make, value}]}` — makes with stock in that year |
| `getAllModelsIISupull` | `make` | `{models: [{model, value}]}` — all models for make |
| `getModelsIISupull` | `year`, `make` | `{models: [{model, value}]}` — year-filtered |
| `getprefilldataIISupull` | `iisYear`, `iisMake` | `{makesSelect, modelsSelect, partsSelect}` — HTML option strings |
| `getpartCategoriesIISupull` | *(none)* | Part categories |

---

## Dedup Key

Use `stock_number` as the stable unique ID. The Set Date tells you when a vehicle was added — sort newest-first to implement incremental runs.

---

## No Recent Arrivals Page

`/latest-arrivals/`, `/recent-arrivals/`, and `/inventory/new/` are all static marketing pages with no vehicle data. For incremental runs, sort all fetched vehicles by Set Date descending and stop when encountering a previously seen stock number.

---

## Request Volume

Approximately 59 makes × avg ~30 models = ~1,770 GET requests for a full crawl. Each is lightweight SSR HTML. No rate limiting observed during recon.
