# Pick Your Part (pyp.com) — LKQ Network

**Site:** https://www.pyp.com  
**Entry point used:** https://www.pyp.com/inventory/cincinnati-1253/  
**Network:** LKQ Corporation subsidiary — **62 locations** across the US, all on the same domain

---

## VIN Availability

> ✅ **VIN IS PRESENT** in the inventory response. Each vehicle card includes a `<b>VIN: </b>` field with the full 17-character VIN.

---

## Platform

**DotNetNuke (DNN)** CMS with a custom `pyp_vehicleInventory` DNN module.

- Module JS: `/DesktopModules/pyp_vehicleInventory/pyp_vehicleInventory.min.js?b=100`
- Inventory endpoint: `/DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx`
- No WordPress, no AJAX admin endpoint

---

## Cloudflare Protection

> ⚠️ **ALL requests (main pages and API endpoints) are protected by Cloudflare managed challenge.**

- `cf-mitigated: challenge` header on all server-side requests
- Returns HTTP 403 with JS challenge page to `curl`, `requests`, etc.
- **Must use a real browser (Playwright) to bypass** — the browser already has the CF clearance cookie from visiting the main page
- No cookies or tokens need to be extracted manually — Playwright's browser context handles this automatically

---

## Inventory API

### Endpoint

```
GET https://www.pyp.com/DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx
    ?page={N}
    &filter={search_text}
    &store={locationCode}
    [&filterDeals=true]
```

**Required header:** `x-requested-with: XMLHttpRequest`

### Response Format

Returns **HTML fragment** (not JSON). Each vehicle is a `div.pypvi_resultRow`.

### Pagination

- **25 vehicles per page**
- Infinite-scroll design — increment `page` from 1
- Continue until response contains `class="pypvi_end"` (no more results)
- Example: Cincinnati (~1,030 vehicles → ~42 pages)

### Sorting

**Newest first** — page 1 always contains the most recently added vehicles. The `Available` date on page 1 can be compared against the last run to implement incremental scraping.

---

## Vehicle Card Data Fields

Each `.pypvi_resultRow` div contains:

| Field | Source | Example |
|-------|--------|---------|
| **Stock ID** | `div#id` → `{locationCode}-{stockNo}` | `1253-37071` |
| **Year/Make/Model** | `.pypvi_ymm` link text | `2003 DODGE DURANGO` |
| **Detail URL** | `.pypvi_ymm` href | `/inventory/cincinnati-1253/2003-dodge-durango/` |
| **Color** | `<b>Color: </b>` detail item | `Brown` |
| **VIN** | `<b>VIN: </b>` detail item | `1D4HS48N53F565790` |
| **Section** | `<b>Section: </b>` detail item | `Trucks/SUV`, `Imports` |
| **Row** | `<b>Row: </b>` detail item | `3` |
| **Space** | `<b>Space: </b>` detail item | `13` |
| **Stock #** | `<b>Stock #:</b>` detail item | `1253-37071` |
| **Available (date added)** | `<time datetime="...">` ISO 8601 UTC | `2026-05-18T18:43:07Z` |
| **Primary image** | `a.pypvi_image[href]` or `img[src]` | `https://cdn.lkqcorp.com/carbuy/CAR-FRONT-LEFT_{photoId}_front_left_corner.jpg` |
| **Additional images** | `div.pypvi_images a[href]` | up to 5 additional angles |

### HTML Parsing Pattern

```python
from bs4 import BeautifulSoup

def parse_inventory_html(html: str, location_code: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    vehicles = []
    for row in soup.select('div.pypvi_resultRow'):
        stock_id = row.get('id', '')  # e.g. "1253-37071"
        ymm_link = row.select_one('a.pypvi_ymm')
        ymm_text = ymm_link.get_text(separator=' ', strip=True) if ymm_link else ''
        
        details = {}
        for item in row.select('div.pypvi_detailItem'):
            b = item.find('b')
            if b:
                key = b.get_text(strip=True).rstrip(':')
                val = item.get_text(strip=True).replace(b.get_text(strip=True), '', 1).strip()
                details[key] = val
        
        time_el = row.select_one('time[datetime]')
        available_iso = time_el['datetime'] if time_el else None
        
        img = row.select_one('a.pypvi_image')
        primary_img = img['href'] if img else None
        
        vehicles.append({
            'stock_id': stock_id,
            'ymm': ymm_text,
            'vin': details.get('VIN'),
            'color': details.get('Color'),
            'section': details.get('Section'),
            'row': details.get('Row'),
            'space': details.get('Space'),
            'stock_number': details.get('Stock #'),
            'available_date': available_iso,
            'primary_image': primary_img,
        })
    return vehicles
```

---

## Scraping Strategy

### Full Inventory Scrape (per location)

1. Launch a Playwright browser and navigate to any `pyp.com` page first (to clear the CF challenge)
2. Loop `page=1, 2, 3, ...` fetching the inventory endpoint via `page.evaluate(() => fetch(...))`
3. Parse each HTML fragment, extract vehicle records
4. Stop when response contains `pypvi_end` CSS class
5. Repeat for each location code

```python
async def scrape_location(playwright_page, location_code: str):
    url_template = (
        f"https://www.pyp.com/DesktopModules/pyp_vehicleInventory/"
        f"getVehicleInventory.aspx?page={{page}}&filter=&store={location_code}"
    )
    page_num = 1
    all_vehicles = []
    while True:
        html = await playwright_page.evaluate(f"""
            async () => {{
                const r = await fetch('{url_template.format(page=page_num)}', {{
                    headers: {{'x-requested-with': 'XMLHttpRequest'}}
                }});
                return r.text();
            }}
        """)
        vehicles = parse_inventory_html(html, location_code)
        all_vehicles.extend(vehicles)
        if 'pypvi_end' in html:
            break
        page_num += 1
    return all_vehicles
```

### Incremental Scrape (subsequent runs)

Since inventory is sorted **newest first**, page 1 = most recent:

1. Record `last_run_date` after each full scrape
2. On subsequent runs, fetch pages starting from page 1
3. Parse `available_date` from each vehicle's `<time datetime="">` field
4. Stop pagination when `available_date < last_run_date` — all older vehicles are already in DB
5. Use `stock_id` (or `vin`) as the dedup key

### Deals/Savings Filter

Append `&filterDeals=true` to get only vehicles with active price promotions. Same pagination and structure applies.

---

## Location Discovery

All 62 locations are embedded in the **inline `_locationList` JS variable** on any inventory page:

```
//<![CDATA[
var _locationList = [{...}, ...];
```

### Extraction

```python
import re, json

def extract_location_list(page_html: str) -> list[dict]:
    match = re.search(r'var _locationList\s*=\s*(\[.*?\]);', page_html, re.DOTALL)
    return json.loads(match.group(1)) if match else []
```

### Location Object Fields

```json
{
  "LocationCode": "1253",
  "Name": "Pick Your Part - Cincinnati",
  "DisplayName": "Cincinnati",
  "Address": "2040 E Kemper Rd",
  "City": "Cincinnati",
  "State": "Ohio",
  "StateAbbr": "OH",
  "Zip": "45241",
  "Phone": "(800) 962-2277",
  "Lat": 39.286363,
  "Lng": -84.43952,
  "LegacyCode": "253",
  "LocationPageURL": "https://locations.lkqpickyourpart.com/en-us/oh/cincinnati/2040-east-kemper-road/",
  "Urls": {
    "Store": "...",
    "Inventory": "/inventory/cincinnati-1253/",
    "Parts": "/parts/cincinnati-1253/",
    "Prices": "/prices/cincinnati-1253/"
  }
}
```

Address, phone, and GPS coordinates are all included — no secondary API calls needed for location details.

### All 62 Locations (as of May 2026)

| Code | Name | City, State |
|------|------|-------------|
| 1253 | Pick Your Part - Cincinnati | Cincinnati, OH |
| 1257 | Pick Your Part - Dayton | Dayton, OH |
| 1254 | Pick Your Part - Fort Wayne | Fort Wayne, IN |
| 1255 | Pick Your Part - South Bend | South Bend, IN |
| 1582 | Pick Your Part - Blue Island | Dixmoor, IL |
| 1585 | Pick Your Part - Chicago South | Chicago, IL |
| 1218 | Pick Your Part - Nashville | Nashville, TN |
| 1348 | Pick Your Part - Grand Rapids | Wayland, MI |
| 1581 | Pick Your Part - Chicago North | Chicago, IL |
| 1217 | Pick Your Part - Chattanooga | Chattanooga, TN |
| 1586 | Pick Your Part - East St. Louis | Washington Park, IL |
| 1256 | Pick Your Part - Milwaukee | Milwaukee, WI |
| 1250 | Pick Your Part - Rockford | Rockford, IL |
| 1213 | Pick Your Part - Greer | Greer, SC |
| 1212 | Pick Your Part - Greenville | Greenville, SC |
| 1223 | Pick Your Part - Huntsville | Huntsville, AL |
| 1228 | Pick Your Part - Charlotte | Charlotte, NC |
| 1226 | Pick Your Part - Greensboro | Greensboro, NC |
| 1142 | Pick Your Part - Durham | Durham, NC |
| 1208 | Pick Your Part - Mount Airy | Mount Airy, MD |
| 1229 | Pick Your Part - Fayetteville | Fayetteville, GA |
| 1168 | Pick Your Part - Raleigh | Clayton, NC |
| 1207 | Pick Your Part - Hawkins Point | Baltimore, MD |
| 1205 | Pick Your Part - Erdman | Baltimore, MD |
| 1215 | Pick Your Part - Memphis | Memphis, TN |
| 1209 | Pick Your Part - Edgewood | Edgewood, MD |
| 1227 | Pick Your Part - East NC | Greenville, NC |
| 1220 | Pick Your Part - Charleston | Charleston, SC |
| 1163 | Pick Your Part - Savannah | Savannah, GA |
| 1746 | Pick Your Part - Tulsa | Tulsa, OK |
| 1224 | Pick Your Part - Gainesville | Gainesville, FL |
| 1246 | Pick Your Part - Wichita | Wichita, KS |
| 1225 | Pick Your Part - Daytona | Daytona Beach, FL |
| 1134 | Pick Your Part - Orlando | Orlando, FL |
| 1245 | Pick Your Part - Oklahoma City | Oklahoma City, OK |
| 1189 | Pick Your Part - Largo | Largo, FL |
| 1180 | Pick Your Part - Tampa | Tampa, FL |
| 1190 | Pick Your Part - Clearwater | Clearwater, FL |
| 1185 | Pick Your Part - Bradenton | Bradenton, FL |
| 1235 | Pick Your Part - Houston Northville | Houston, TX |
| 1236 | Pick Your Part - Houston Wallisville | Houston, TX |
| 1196 | Pick Your Part - West Palm Beach | West Palm Beach, FL |
| 1239 | Pick Your Part - Houston SW | Houston, TX |
| 1234 | Pick Your Part - Austin | Austin, TX |
| 1230 | Pick Your Part - Aurora | Aurora, CO |
| 1231 | Pick Your Part - Denver 52nd Ave | Denver, CO |
| 1287 | Pick Your Part - Victorville | Victorville, CA |
| 1292 | Pick Your Part - Hesperia | Hesperia, CA |
| 1291 | Pick Your Part - San Bernadino | San Bernardino, CA |
| 1284 | Pick Your Part - Rialto | Bloomington, CA |
| 1285 | Pick Your Part - Fontana | Fontana, CA |
| 1290 | Pick Your Part - Riverside | Riverside, CA |
| 1280 | Pick Your Part - Ontario | Ontario, CA |
| 1264 | Pick Your Part - Chula Vista | Chula Vista, CA |
| 1281 | Pick Your Part - Monrovia | Monrovia, CA |
| 1282 | Pick Your Part - Santa Fe Springs | Santa Fe Springs, CA |
| 1265 | Pick Your Part - Anaheim | Anaheim, CA |
| 1263 | Pick Your Part - Sun Valley | Sun Valley, CA |
| 1262 | Pick Your Part - Wilmington Help Yourself | Wilmington, CA |
| 1260 | Pick Your Part - Bakersfield | Bakersfield, CA |

---

## URL Patterns

```
Inventory page:   /inventory/{slug}-{locationCode}/
Savings/deals:    /inventory/{slug}-{locationCode}/savings/
Parts search:     /parts/{slug}-{locationCode}/
Prices:           /prices/{slug}-{locationCode}/
Location detail:  https://locations.lkqpickyourpart.com/en-us/{state}/{city}/{address}/
```

---

## Images

Images are served from LKQ's CDN:

```
https://cdn.lkqcorp.com/carbuy/{VIEW}_{photoId}_{description}.jpg
```

The photo ID (numeric) is embedded in the image URL and is independent of the stock number.

Standard quality parameters:
- Full size: `?quality=35`
- Thumbnail: `?w=100&h=72&mode=crop&quality=70`
- Card size: `?quality=65&w=260&h=150&mode=crop`

---

## Notes

- The `savings/` filter page is useful for targeted scraping of vehicles with active promotions, but does not provide a subset useful for dedup — use the main inventory with `available_date` comparison instead.
- All 62 locations share a single phone number `(800) 962-2277` (LKQ corporate); a few FL locations use `(800) 962-CARS`.
- Location slugs in URLs are deterministic from `DisplayName` (lowercased, spaces to hyphens) + `-` + `LocationCode`.
