# Central Florida Pick & Pay — Inventory Scraping Strategy

**Site:** https://centralfloridapickandpay.com  
**Locations:** 1 yard (Orlando, FL)

---

## VIN Availability

VIN **IS** available. Full 17-character VIN is a column in every row of the inventory table.

---

## Location & Contact Info

| Field | Value |
|-------|-------|
| **Address** | 10694 Cosmonaut Blvd, Orlando, FL 32824 |
| **Phone** | 407-783-7985 |
| **Sales Email** | sales@centralfloridapickandpay.com |
| **General Email** | hello@centralfloridapickandpay.com |
| **Google Maps** | https://goo.gl/maps/1vvxdq5ZUmAi6orD9 |
| **Entrance Fee** | $3.00 |

### Hours

| Day | Open | Close |
|-----|------|-------|
| Monday | 8:00 AM | 4:30 PM |
| Tuesday | 8:00 AM | 4:30 PM |
| Wednesday | 8:00 AM | 4:30 PM |
| Thursday | 8:00 AM | 6:30 PM |
| Friday | 8:00 AM | 6:30 PM |
| Saturday | 8:00 AM | 6:30 PM |
| Sunday | 8:00 AM | 4:30 PM |

*On holidays opening hours may be different.*

---

## Inventory Data Source — Single SSR Page (Extremely Simple)

The entire inventory (~1,275 vehicles as of May 2026) is **server-side rendered** into a single HTML page at `/vehicle-inventory/`. The site uses a custom WordPress plugin (`vehicle-inventory`) that writes all rows into a `<table id="vehicles">` at page-render time. DataTables is used purely for client-side pagination/sorting — no AJAX, no server-side processing.

**One `requests.get()` call returns the complete inventory.**

### Table Schema

Columns in the `<table id="vehicles">` (in order, 0-indexed):

| Index | Column | Description |
|-------|--------|-------------|
| 0 | Year | Model year |
| 1 | Make | Vehicle make (uppercase) |
| 2 | Model | Vehicle model (uppercase) |
| 3 | Color | Exterior color (uppercase) |
| 4 | Engine | Engine description (e.g. `V8, 4.2L; SUPERCHARGED`) |
| 5 | Row | Yard row number where the vehicle is located |
| 6 | Arrival Date | Date added to yard (`MM/DD/YY`) |
| 7 | VIN | Full 17-character VIN |

The `<td>` elements have a `data-label` attribute matching the column name — useful for robust parsing.

### Example Row (from live data)

```
2006 | LAND ROVER | RANGE ROVER | BLACK | V8, 4.2L; SUPERCHARGED | 102 | 05/15/26 | SALMF13466A200123
```

---

## Scraping Strategy

### Full Inventory Fetch

```python
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://centralfloridapickandpay.com/vehicle-inventory/"

def fetch_inventory() -> list[dict]:
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "vehicles"})
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 8:
            continue
        rows.append({
            "year": cells[0].text.strip(),
            "make": cells[1].text.strip(),
            "model": cells[2].text.strip(),
            "color": cells[3].text.strip(),
            "engine": cells[4].text.strip(),
            "row": cells[5].text.strip(),
            "arrival_date": cells[6].text.strip(),  # MM/DD/YY
            "vin": cells[7].text.strip(),
            "yard": "Central Florida Pick & Pay",
            "location": "Orlando, FL",
        })
    return rows
```

### Incremental Updates (Recent Arrivals)

The table is **sorted by Arrival Date descending** (DataTables `order: [[ 6, 'desc' ]]`), so the most recently added vehicles appear first in the raw HTML. There is **no dedicated recent arrivals page**; use the first page of results from the main table.

**Suggested incremental strategy:**
1. Fetch the full page HTML.
2. Parse all rows — stop at the first row whose `arrival_date` is older than the last run's most recent date.
3. If all rows are new (first run), ingest everything.

```python
def fetch_new_arrivals(since_date: str) -> list[dict]:
    """
    since_date: 'MM/DD/YY' — skip rows with arrival_date <= since_date
    Table is arrival-date-desc, so we can stop early once we hit known dates.
    """
    all_rows = fetch_inventory()
    new_rows = [r for r in all_rows if r["arrival_date"] > since_date]
    return new_rows
```

> **Note:** Date format is `MM/DD/YY` (two-digit year). Compare as strings only if zero-padded and within the same century, otherwise parse with `datetime.strptime(d, "%m/%d/%y")`.

---

## Technical Notes

### WordPress Plugin

The custom plugin lives at:
```
/wp-content/plugins/vehicle-inventory/
```

There is one non-scraping endpoint:
```
GET /wp-content/plugins/vehicle-inventory/veihicleInventorySelectedMake.php
    ?selectedMake=FORD&selectedModel=
```
This returns HTML `<option>` elements for the model dropdown when a make is selected. **Not needed for scraping** — all data is already in the main table.

### No Auth Required

- No nonce
- No session cookie
- No Cloudflare challenge
- Standard `requests.get()` works server-side without any headers

### Single Location

This is a single-yard operation. No location ID or location filtering is needed.

---

## Summary

| Property | Value |
|----------|-------|
| Locations | 1 |
| Fetch calls needed | 1 |
| Auth required | None |
| VIN available | Yes |
| Recent arrivals page | No (table sorted by arrival date desc) |
| Approximate inventory size | ~1,275 vehicles |
| Update frequency | Daily |
