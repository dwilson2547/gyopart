# Pull-N-Save Inventory Scraper Research

**Site:** https://www.pullnsave.com/inventory/  
**Date Researched:** 2026-05-18  
**Status:** Research complete, scraper not yet built

---

## Site Overview

Pull-N-Save is a self-serve auto parts junkyard chain with 8 locations across Utah, Arizona, and California. Their website provides a public inventory search at `/inventory/` and `/inventory-search/`.

The site runs on WordPress with two custom plugins layered on top of each other:
- **Legacy plugin** (`gm_vehicle_search` / `PnsV1_3.3`) — older approach, AJAX returns HTML, no auth required
- **Newer plugin** (`pns-vehicle-search`) — newer approach, AJAX returns JSON, requires a WordPress nonce

---

## Locations / Store Numbers

Retrieved via `getStores` action (no auth needed):

| StoreNumber | StoreName            | State |
|-------------|----------------------|-------|
| 1           | Salt Lake City       | UT    |
| 2           | Phoenix - South      | AZ    |
| 3           | Glendale             | AZ    |
| 4           | Phoenix - North      | AZ    |
| 5           | Gilbert              | AZ    |
| 6           | Springville          | UT    |
| 7           | Tucson               | AZ    |
| 9           | Riverside            | CA    |

---

## API Endpoints

### 1. WordPress Admin AJAX (Primary)

**Base URL:** `https://www.pullnsave.com/wp-admin/admin-ajax.php`  
**Method:** `POST`  
**Content-Type:** `application/x-www-form-urlencoded`

All legacy actions work **without authentication** from server-side. The newer `pns_get_inventory_assets` action is blocked by a WAF/firewall when called without a valid browser session.

---

#### `getStores` — Returns all yard locations

```
POST /wp-admin/admin-ajax.php
action=getStores
```

**Response:** JSON array
```json
[
  {"StoreNumber": "1", "StoreName": "Salt Lake City", "State": "UT"},
  {"StoreNumber": "2", "StoreName": "Phoenix - South", "State": "AZ"},
  ...
]
```

---

#### `getMakes` — Returns all vehicle makes in inventory

```
POST /wp-admin/admin-ajax.php
action=getMakes
```

**Response:** HTML `<option>` elements (parse with BeautifulSoup/lxml)  
**Optional filter param:** `year=YYYY` — narrows makes to those with vehicles of that year

**Makes (as of 2026-05-18):** Acura, Alfa-Romeo, AM General, Audi, BMW, Chrysler, Daewoo, Daihatsu, Dodge, Fiat-Lancia, Ford, General Motors, Genesis, Honda, Hyundai, Infiniti, International, Isuzu, Jaguar, Jeep, Kia, Lexus, Mazda, Mercedes-Benz, MINI Cooper, Mitsubishi, Nissan, Peugeot, Porsche, Renault, Rover, Saab, Scion, Subaru, Suzuki, Toyota, Volkswagen, Volvo

---

#### `getModels` — Returns models for a given make

```
POST /wp-admin/admin-ajax.php
action=getModels
Make=Honda
Year=2005
endYear=2010
Form=searchVehicleForm
```

**Response:** HTML `<option>` elements

---

#### `getYears` — Returns available years for a make/model

```
POST /wp-admin/admin-ajax.php
action=getYears
Make=Honda
Model=Civic
```

**Response:** HTML `<option>` elements

---

#### `getVehicles` — **Primary scraping target**

Returns current inventory as an HTML table. Works with store and make filters. No auth required.

```
POST /wp-admin/admin-ajax.php
action=getVehicles
makes=Honda
models=0          # 0 = any model
store=1           # StoreNumber from getStores, 0 = all stores
action=getVehicles
```

**Response:** HTML containing a `<table id="vehicletable1">` (FooTable format)

**Columns:**
- `[img]` — thumbnail (links to image API below)
- `Year`
- `Model`
- `Date Received` (data-value attribute has ISO date: `2026-05-15`)
- `Row` — physical yard row number
- `Store` — store name string (e.g., "Salt Lake City")
- `Color`
- `Stock#` — e.g., `STK130261`
- `VIN`

**Example curl:**
```bash
curl -s -X POST 'https://pullnsave.com/wp-admin/admin-ajax.php' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'action=getVehicles&store=1&makes=Honda&models=0'
```

**Caveats:**
- Response is HTML, not JSON — requires HTML parsing
- Unknown if results are paginated or truncated for large sets; recommend combining make + store filters
- `makes=` uses the **text value** from `getMakes` (e.g., `Honda`, not an ID)

---

#### `pns_get_inventory_assets` — Newer JSON endpoint (harder to use)

```
POST /wp-admin/admin-ajax.php
action=pns_get_inventory_assets
search_type=0          # 0=yard, 1=zip
yearStart=2010
yearEnd=2015
make=HONDA             # text of make option (not ID)
model=0                # 0 = all models
yard[]=1               # array of StoreNumbers
zip=
radius=0
security=<nonce>       # WordPress nonce from inventory page HTML
```

**Response:** JSON
```json
{
  "success": true,
  "data": [
    {
      "stockId": "STK130261-1",
      "year": 2005,
      "make": "HONDA",
      "model": "ODYSSEY",
      "vin": "5FNRL38775B051201",
      "color": "BLUE",
      "yardRow": 6,
      "yardName": "Pull N Save - Salt Lake City",
      "yardAddress": "...",
      "yardZip": "...",
      "rcvdDtTm": "2026-05-15T09:00:00"
    }
  ]
}
```

**Nonce extraction** (from `/inventory/` page source):
```html
var pns_inventory_sf_ajax = {
  "url": "https://www.pullnsave.com/wp-admin/admin-ajax.php",
  "nonce": "7108a5df33",
  "apiurl": "https://app.pullnsaveapp.com/v1/Vehicles/Search"
};
```
Regex: `"nonce":"([^"]+)"`

**Status:** The server-side AJAX call returns a 403 from a WAF/CDN when called without proper browser fingerprinting. The legacy `getVehicles` endpoint is the reliable alternative.

---

### 2. Direct Backend API (Mobile App)

**Base URL:** `https://app.pullnsaveapp.com/v1/`  
**Method:** `POST`  
**Content-Type:** `application/json`  
**Auth:** None required from server-side  
**CORS:** Blocked in browser, but accessible via Python `requests` / curl

```
POST https://app.pullnsaveapp.com/v1/Vehicles/Search
Content-Type: application/json

{
  "yearStart": 0,
  "yearEnd": 0,
  "make": "HONDA",
  "model": "",
  "yard": [1],
  "searchType": 0,
  "zip": "",
  "radius": 0
}
```

**Response:** JSON array (hard-capped at **100 records**)
```json
[
  {
    "astStoreNumber": 1,
    "vehicleRno": 132754,
    "storeRno": 1,
    "stockId": "STK128057-1",
    "rcvdDtTm": "2026-02-10T08:23:00",
    "vin": "5FNRL387X8B037605",
    "year": 2008,
    "make": "HONDA",
    "model": "ODYSSEY",
    "color": "BLUE",
    "transmissionDesc": null,
    "engineDesc": null,
    "yardRow": 8
  },
  ...
]
```

**Known Limitations:**
- Always returns `storeRno: 1` regardless of `yard` filter — may only serve one location's data
- Hard cap of 100 records per response — no pagination discovered
- Data may lag by weeks compared to the WP AJAX endpoints
- `transmissionDesc` and `engineDesc` are always `null` in observed responses

**Example curl:**
```bash
curl -s -X POST 'https://app.pullnsaveapp.com/v1/Vehicles/Search' \
  -H 'Content-Type: application/json' \
  -d '{"yearStart":0,"yearEnd":0,"make":"HONDA","model":"","yard":[1],"searchType":0}'
```

---

### 3. Vehicle Image API

Vehicle photos are available at a predictable URL — no auth required:

```
https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/{stockId}/OrderId/{N}
```

- `{stockId}` — full stock ID with suffix, e.g., `STK130261-1`
- `{N}` — image order, 1 through 4

**Example:**
```
https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/STK130261-1/OrderId/1
```

---

## Form Field Reference

The search form at `/inventory/` uses these field names (useful for replicating via `pns_get_inventory_assets`):

| HTML Field     | Name           | Description                           |
|----------------|----------------|---------------------------------------|
| `pns_year`     | `pns_years`    | Year or range, e.g., `2010` or `1975-1980` |
| `pns_make`     | `pns_make`     | Make ID (numeric, from select options) |
| `pns_model`    | *(none)*       | Model select (populated after make)   |
| `yard_radio`   | `search_type`  | `0` = select yard, `1` = zip code     |
| `pns_yard`     | *(none)*       | Multi-select of yard IDs              |
| `pns_zip`      | `zipcode`      | Zip code (for zip-based search)       |
| `pns_radius`   | *(none)*       | Radius: 10, 25, 30, 40, or 50+ miles  |

**Make IDs** (from the `pns_make` select in the search form):

| ID  | Make         | ID  | Make        |
|-----|--------------|-----|-------------|
| 1   | CHEVROLET    | 14  | CHRYSLER    |
| 2   | VOLKSWAGEN   | 15  | SUBARU      |
| 3   | HYUNDAI      | 16  | GMC         |
| 4   | HONDA        | 17  | MERCURY     |
| 5   | FORD         | 18  | MITSUBISHI  |
| 6   | NISSAN       | 19  | KIA         |
| 7   | BUICK        | 20  | TOYOTA      |
| 8   | PONTIAC      | 21  | ACURA       |
| 9   | DODGE        | 22  | LINCOLN     |
| 10  | CADILLAC     | 25  | BMW         |
| 11  | SATURN       | 27  | MAZDA       |
| 12  | JEEP         | 29  | MERCEDES-BENZ |
| 13  | INFINITI     | 40  | RAM         |

> Note: The `pns_get_inventory_assets` endpoint uses the **text name** of the make (e.g., `HONDA`), not the numeric ID.

---

## Recommended Scraping Strategy

### Approach: Iterate `getVehicles` by Store × Make

The most reliable full-inventory approach with no auth required:

```python
import requests
from bs4 import BeautifulSoup

AJAX_URL = "https://pullnsave.com/wp-admin/admin-ajax.php"
STORES = [1, 2, 3, 4, 5, 6, 7, 9]
MAKES = [...]  # fetch from getMakes endpoint first

for store in STORES:
    for make in MAKES:
        resp = requests.post(AJAX_URL, data={
            "action": "getVehicles",
            "store": store,
            "makes": make,
            "models": "0",
        })
        soup = BeautifulSoup(resp.text, "html.parser")
        # parse <table id="vehicletable1"> rows
```

**Deduplication:** Use `StockId` as the unique key across all results.

### Scheduling

- Inventory changes daily (cars added/removed)
- Recommend a daily scrape per store
- Rate-limit requests (1–2 seconds between calls) to avoid triggering WAF

### Data Fields to Capture

| Field        | Source                | Notes                            |
|--------------|-----------------------|----------------------------------|
| `stock_id`   | HTML / API            | Primary key, e.g., `STK130261`  |
| `store_number` | request param      | 1–9                              |
| `store_name` | HTML response         | e.g., "Salt Lake City"           |
| `year`       | HTML / API            |                                  |
| `make`       | HTML / API            |                                  |
| `model`      | HTML / API            |                                  |
| `color`      | HTML / API            |                                  |
| `vin`        | HTML / API            |                                  |
| `yard_row`   | HTML / API            | Physical row in yard             |
| `date_added` | HTML `data-value`     | ISO date, e.g., `2026-05-15`    |
| `image_url`  | Constructed           | `app.pullnsaveapp.com/v1/...`    |
| `scraped_at` | Runtime               | Timestamp of scrape              |

---

## Anti-Scraping Observations

- The `wp-admin/admin-ajax.php` endpoint is behind a Cloudflare WAF
- Legacy AJAX actions (`getVehicles`, `getStores`, `getMakes`) work from server-side without a browser fingerprint
- The newer `pns_get_inventory_assets` action returns 403 without proper browser session headers
- No rate limiting observed on the direct `app.pullnsaveapp.com` API (but 100-record cap)
- No `robots.txt` blocking of inventory pages observed

---

## Open Questions / TODOs

- [ ] Confirm whether `getVehicles` with `store=0` returns all stores or just one
- [ ] Test if results are truncated when a make has many vehicles in a store (need count validation)
- [ ] Check if `getVehicles` supports a date range filter to detect only new additions
- [ ] Investigate whether `app.pullnsaveapp.com/v1/Vehicles/Search` can be made to return data for stores 2–9
- [ ] Determine if `beginDate`/`endDate` params in the old search form filter by `rcvdDtTm`
- [ ] Explore part-level inventory endpoints (`getICOptionsForPart`, `getPartTypesWithIC`, `getFitmentListing`)
- [ ] Check if the `inventory-search` URL query string format allows for direct full-inventory fetches
