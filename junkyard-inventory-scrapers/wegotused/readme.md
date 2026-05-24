# wegotused.com — Harry's U-Pull It

**URL:** https://wegotused.com/our-inventory/  
**Business Name:** Harry's U-Pull It  
**Platform:** WordPress + custom `inventory-7lt` plugin (AngularJS 1.7.8 front-end)  
**Theme:** Avada

---

## VIN Availability

**VINs ARE present** in every table row across all inventory pages.

---

## Locations

| Yard | Address | Phone |
|------|---------|-------|
| Allentown | 1510 East Jonathan Street, Allentown, PA | (610) 433-9901 |
| Pennsburg | 2557 Geryville Pike, Pennsburg, PA 18073 | (215) 541-9950 |
| Hazle Township | 1010 Winters Avenue, Hazle Township, PA 18202 | (570) 459-9901 / 1-888-514-9901 |

Yard names in inventory rows match these city names exactly (`ALLENTOWN`, `PENNSBURG`, `HAZLE TOWNSHIP`).

---

## Platform Notes

The `inventory-7lt` plugin renders the inventory table **server-side** on page load. AngularJS handles filtering UI and uses `jQuery("#_results").load(url + " #_results")` to reload the results div on filter changes. The initial HTML response always contains full table data — no JavaScript execution required to scrape.

No admin-ajax, no nonce, no auth — plain HTTP GET throughout.

---

## Scraping Strategy

### Inventory Endpoint

```
GET https://wegotused.com/our-inventory/?inv[yard]=all&inv[make]=&inv[model]=&inv[manufacturer]=&inv[year]=&inv[part]=&inv[page]={N}&inv[sort][yard_date]=0
```

- `inv[page]` is **0-indexed** (page=0 → records 1–15, page=1 → records 16–30, etc.)
- `inv[sort][yard_date]=0` — newest first; `=1` — oldest first
- Response is a full HTML page; extract the `#_results` element to avoid parsing the full page

### Pagination

Total record count is embedded in the results:
```
Showing 1 to 15 of 4111 records
```

```python
import math, re, requests
from bs4 import BeautifulSoup

BASE = "https://wegotused.com/our-inventory/"
PARAMS = "inv[yard]=all&inv[make]=&inv[model]=&inv[manufacturer]=&inv[year]=&inv[part]="

def get_page(n, sort_date=0):
    url = f"{BASE}?{PARAMS}&inv[page]={n}&inv[sort][yard_date]={sort_date}"
    return requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

# Step 1: get total count
r = get_page(0)
soup = BeautifulSoup(r.text, "html.parser")
results_div = soup.select_one("#_results")
count_text = results_div.get_text()
total = int(re.search(r"of (\d+) records", count_text).group(1))
total_pages = math.ceil(total / 15)

# Step 2: loop all pages
for page_num in range(total_pages):
    r = get_page(page_num)
    soup = BeautifulSoup(r.text, "html.parser")
    results_div = soup.select_one("#_results")
    for row in results_div.select("tbody tr"):
        cells = [td.get_text(strip=True) for td in row.select("td")]
        if len(cells) < 9:
            continue
        record = {
            "yard_city":    cells[0],   # e.g. "ALLENTOWN"
            "year":         cells[1],
            "make":         cells[2],
            "model":        cells[3],
            "manufacturer": cells[4],
            "color":        cells[5],
            "yard_date":    cells[6],   # MM/DD/YYYY
            "row":          cells[7],
            "vin":          cells[8],
        }
        # item detail URL (if needed):
        info_link = row.select_one("a[href*='/inventory-item/']")
        if info_link:
            record["detail_url"] = "https://wegotused.com" + info_link["href"]
```

### Table Columns

| Column | Example |
|--------|---------|
| Yard City | `ALLENTOWN` |
| Year | `2012` |
| Make | `HYUNDAI` |
| Model | `ACCENT` |
| Manufacturer | `Hyundai` |
| Color | `RED` |
| Yard Date | `05/14/2026` |
| Row | `105` |
| VIN | `KMHCT5AE1CU042343` |

### Filtering by Yard

To restrict to a single location:
```
inv[yard]=ALLENTOWN   (or PENNSBURG, HAZLE+TOWNSHIP)
```

### JSON API Endpoints

These return JSON and are useful for building filter dropdowns:

```
GET /our-inventory/?inv_action=get_makes
→ [{"make":"ACURA"}, {"make":"HONDA"}, ...]

GET /our-inventory/?inv_action=get_models&inv[make]={MAKE}
→ [{"model":"ACCORD"}, ...]

GET /our-inventory/?inv_action=get_years&inv[mfr]={MFR_CODE}&inv[model]={MODEL}
→ year list

GET /our-inventory/?inv_action=get_parts
→ parts list
```

These are not required for a full inventory crawl — they're only used for the search form.

---

## Incremental / Subsequent Runs

Sort by newest first (`inv[sort][yard_date]=0`) and walk pages from page 0 until you encounter a VIN already in your database:

```python
for page_num in range(total_pages):
    r = get_page(page_num, sort_date=0)  # newest first
    # parse rows...
    for record in rows:
        if record["vin"] in known_vins:
            # done — all remaining records are older
            raise StopIteration
        # else persist record
```

**Note:** Multiple vehicles can share the same `yard_date`, so don't stop on first date match — stop only on a VIN match. There is no dedicated "recent arrivals" page; sorted pagination is the equivalent.

---

## Item Detail Page

`GET https://wegotused.com/inventory-item/item-{ID}`

Contains the same fields as the table plus a "Last Updated" timestamp, but is **AngularJS-rendered** — you must run JavaScript to read it. The inventory table already provides all useful fields; individual item pages are not required for a full crawl.
