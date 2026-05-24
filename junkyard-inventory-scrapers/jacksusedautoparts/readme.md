# Jack's Used Auto Parts — Inventory Scraper Strategy

**Site:** https://jacksusedautoparts.com/vehicle-inventory/  
**Data endpoint:** https://jacksusedautoparts.com/vehicleInventory.php  
**Recon date:** 2026-05-19

---

> [!CAUTION]
> ## ⚠️ NO VIN AVAILABLE
> The inventory table has **zero VIN data**. There are no VIN columns, no hidden VIN attributes,
> no 17-character alphanumeric strings anywhere in the HTML response. Deduplication must rely on
> a composite key. Cross-referencing with other systems will be severely limited.

---

## Location

Single yard — no multi-location support.

| Field   | Value                                    |
|---------|------------------------------------------|
| Name    | Jack's Used Auto Parts                   |
| Address | 4500 Kellogg Ave, Cincinnati, Ohio 45226 |
| Phone   | 513-321-7775                             |
| Hours   | Weekdays 8:30am–4:45pm, Saturday 8:30am–4:45pm, Sunday closed |

---

## Data Source

The inventory page (`/vehicle-inventory/`) embeds an `<iframe src="/vehicleInventory.php">`.
That PHP file returns the **complete inventory as a single SSR HTML table** (~1,092 rows as of
recon). DataTables handles client-side pagination and search — no server-side paging occurs.

**A single `GET https://jacksusedautoparts.com/vehicleInventory.php` with a browser User-Agent
returns the full inventory.** No auth, no session, no CSRF token, no cookies required.

The page is nginx-cached (`x-cache-status: HIT`) and includes a timestamp in the response body
(`Updated: May 18, 2026 19:56:29`). The cache appears to refresh daily, sometime in the evening.

---

## Response Structure

HTML table: `<table id="vehicles">` with the following columns:

| Column        | `data-label` | Notes                                     |
|---------------|--------------|-------------------------------------------|
| Year          | `Year`       | 4-digit integer string                    |
| Make          | `Make`       | All caps, e.g. `CHEVROLET`               |
| Model         | `Model`      | All caps, e.g. `SILVERADO`               |
| Color         | `Color`      | All caps; may be blank                    |
| Engine        | `Reference`  | e.g. `3.4L`; frequently blank             |
| Vehicle Row   | `Row`        | Integer yard row number                   |
| Arrival Date  | `Arrived`    | Format `MM/DD/YY`, e.g. `05/16/26`       |

Default sort: Arrival Date descending (newest first).

---

## Scraping Strategy

```python
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://jacksusedautoparts.com/vehicleInventory.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def scrape():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Extract "Updated:" timestamp from the top of the response
    # Pattern: "Updated: May 18, 2026 19:56:29\n"
    updated_at = None
    first_line = resp.text.split("\n")[0].strip()
    if first_line.startswith("Updated:"):
        updated_at = first_line.replace("Updated:", "").strip()

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", id="vehicles")
    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        rows.append({
            "year":         cells[0].get_text(strip=True),
            "make":         cells[1].get_text(strip=True),
            "model":        cells[2].get_text(strip=True),
            "color":        cells[3].get_text(strip=True),
            "engine":       cells[4].get_text(strip=True),
            "vehicle_row":  cells[5].get_text(strip=True),
            "arrival_date": cells[6].get_text(strip=True),
        })
    return {"updated_at": updated_at, "vehicles": rows}
```

### Deduplication

No VIN available. Use a composite key:

```
{year}|{make}|{model}|{color}|{engine}|{vehicle_row}|{arrival_date}
```

This composite should be stable per vehicle since all fields are static after arrival. Vehicle Row
is the most stable distinguishing field alongside arrival date.

### Incremental Runs

The table is sorted by Arrival Date descending by default. On subsequent runs:
1. Fetch the full page (it's ~385KB, one request).
2. Extract the `Updated:` timestamp from the first line — if it matches the last stored timestamp,
   the inventory has not changed; skip processing.
3. Otherwise, compare all rows against the stored composite keys. New keys = new arrivals.
4. Rows that have disappeared since last run = crushed/sold vehicles.

---

## Recent Arrivals

No dedicated recent arrivals endpoint exists. The main inventory table is sorted by Arrival Date
descending by default, so the newest vehicles appear first. Use the `arrival_date` field to
filter for vehicles added since the last run.

---

## Notes

- `x-frame-options: SAMEORIGIN` is set, meaning the iframe can only be embedded by the same
  origin. This is irrelevant for scraping since we fetch the PHP URL directly.
- The "Engine" column label in the HTML source uses `data-label="Reference"` (not "Engine").
  The visible column header says "Engine". Use the `data-label` attribute if parsing by label.
- The `Updated:` timestamp on line 1 of the response body (before any HTML) is reliable for
  cache-busting checks — compare it before parsing the whole table.
