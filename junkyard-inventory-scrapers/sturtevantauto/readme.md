# Sturtevant Auto — Inventory Scraping Strategy

> **⚠️ NO VIN AVAILABLE**
> The inventory table does not expose VINs anywhere — not in the HTML, not in hidden fields, not in image filenames. The "REFERENCE" column contains engine specs (e.g. `V6, 3.2L; SOHC 24V`), not a VIN. Any downstream system that requires VIN for matching cannot be satisfied from this source alone.

---

## Location

Single yard — no multi-location support.

| Field   | Value                              |
|---------|------------------------------------|
| Address | 2145 N. East Frontage Rd. I-94     |
| City    | Sturtevant, WI 53177               |
| Phone   | 262-835-2300                       |
| Hours   | Mon–Fri 8:00am–5:00pm, Sat 8:00am–3:00pm, Sun 9:00am–2:00pm |
| Web     | https://www.sturtevantauto.com/    |

---

## Platform

Custom self-hosted **legacy ASP.NET MVC** application (not ASP.NET Core).

Key identifiers:
- Scripts served from `/Scripts/jquery-3.3.1.js`, `/Scripts/bootstrap.min.js` etc.
- Bundle paths (`/bundles/jquery`, `/bundles/bootstrap`) return **404** — only the direct script paths load.
- No `__RequestVerificationToken` anti-forgery field in forms (classic MVC, not Core Data Protection).
- Inventory subdomain: `inventory.sturtevantauto.com`; main site: `www.sturtevantauto.com`

---

## Inventory Data Fields

| Column       | Notes                                       |
|--------------|---------------------------------------------|
| IMAGE        | Link/thumbnail — see image URL pattern below |
| YEAR         | 4-digit model year                          |
| MAKE         | e.g. `HONDA`                                |
| MODEL        | e.g. `CIVIC`                                |
| COLOR        | Plain English color name                    |
| REFERENCE    | Engine spec string — **not a VIN**          |
| STOCK #      | Internal stock ID, e.g. `STK046039`         |
| ROW          | Yard row number where vehicle is parked     |
| ARRIVAL DATE | `MM/DD/YYYY` — useful for incremental runs  |

**Image URL pattern:**
```
https://inventory.sturtevantauto.com/InventoryPhotos/{STOCK}.JPG
```

---

## Scraping Strategy

### 1. Enumerate Makes

Load the homepage to extract all makes from the dropdown:

```
GET https://inventory.sturtevantauto.com/
```

Parse `<select id="car-make"> <option value="{MAKE}">{MAKE}</option>` entries (skip the first `Select Make` placeholder).

As of investigation (May 2026), makes include:
`ACURA, AUDI, BMW, BUICK, CADILLAC, CHEVROLET, CHRYSLER, DODGE, FORD, GMC, HONDA, HUMMER, HYUNDAI, INFINITI, ISUZU, JAGUAR, JEEP, KIA, LAND ROVER, LEXUS, LINCOLN, MAZDA, MERCEDES-BENZ, MERCURY, MITSUBISHI, NISSAN, OLDSMOBILE, PLYMOUTH, PONTIAC, RAM, SAAB, SATURN, SCION, SMART, SUBARU, TOYOTA, VOLKSWAGEN, VOLVO`

### 2. Fetch All Vehicles Per Make

For each make, POST to the root with an **empty model** — the server returns all vehicles for that make regardless of model:

```
POST https://inventory.sturtevantauto.com/
Content-Type: application/x-www-form-urlencoded

VehicleMake=FORD&VehicleModel=
```

- No CSRF/anti-forgery token required.
- No pagination — all vehicles for the make are returned in a single response.
- Response is full-page SSR HTML; extract the `<table class="table">` body.

FORD returned ~108 rows in one response, so sizes are manageable.

### 3. Parse Table Rows

Each `<tr>` after the header corresponds to one vehicle:

```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, 'html.parser')
table = soup.find('table', class_='table')
rows = table.find_all('tr')[1:]  # skip header
for row in rows:
    cols = row.find_all('td')
    vehicle = {
        'image_url': 'https://inventory.sturtevantauto.com' + cols[0].find('img')['src'].lstrip('..'),
        'year':         cols[1].text.strip(),
        'make':         cols[2].text.strip(),
        'model':        cols[3].text.strip(),
        'color':        cols[4].text.strip(),
        'reference':    cols[5].text.strip(),  # engine spec, NOT VIN
        'stock_number': cols[6].text.strip(),
        'row':          cols[7].text.strip(),
        'arrival_date': cols[8].text.strip(),  # MM/DD/YYYY
    }
```

### 4. Optional — Incremental / Delta Runs

`ARRIVAL DATE` is present on every row. On subsequent runs, compare the newest `arrival_date` seen in the last run against current results. If all top records match known dates, you can stop early (similar to a "recent arrivals" page signal).

There is no dedicated `/recent-arrivals` endpoint.

---

## Auxiliary API Endpoint (not needed for full scrape)

The make dropdown change triggers an AJAX call that the scraper does not need, but is documented here for completeness:

```
POST https://inventory.sturtevantauto.com/Home/GetModels
Content-Type: application/x-www-form-urlencoded

makeName=FORD&showInventory=true
```

Returns JSON:
```json
[{"model":"BRONCO"},{"model":"EDGE"},{"model":"ESCAPE"}, ...]
```

This is only useful if you need to filter by model. The POST-with-empty-model approach above is simpler for a full inventory pull.

---

## No Recent Arrivals Page

No `/recent`, `/new-arrivals`, or similar endpoint was found. The `ARRIVAL DATE` field in the results table serves as the functional equivalent.

---

## Session / Authentication

None required. No login, no cookies needed beyond normal session state for the page load. `requests.Session()` is still recommended to share cookies across GET + POST calls.
