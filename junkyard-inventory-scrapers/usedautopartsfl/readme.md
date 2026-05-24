# ABC Used Auto Parts FL (usedautopartsfl.com)

## Location

**ABC Used Auto Parts**  
18609 East Colonial Drive (Lot #3)  
Orlando, FL 32820  
~6 miles east of Alafaya Trail on Hwy 50  

**Phone:** 407-287-5100 / 407-568-6550 / 888-827-9077  
**Email:** abcusedauto@gmail.com  
**Owner email:** junkcarsfl@gmail.com  
**eBay store:** https://www.ebay.com/str/abcusedautopartsfl  

**Single-location yard.**

---

## Inventory Access Strategy

The site embeds an [AppSheet](https://appsheet.com) app as an iframe. AppSheet is backed by
a **public Google Spreadsheet** — the underlying Google Sheet is accessible as a direct CSV export
**with no authentication, no API key, and no session required.**

### Primary Method — Google Sheets CSV Export

All 5 inventory tables live in the same spreadsheet:

```
DocId: 1HySo6ksil-jl6McltcYui6TBC7UvOCMqd754uw4EpOc
URL:   https://docs.google.com/spreadsheets/d/1HySo6ksil-jl6McltcYui6TBC7UvOCMqd754uw4EpOc
```

Export a sheet as CSV:
```
https://docs.google.com/spreadsheets/d/{DOC_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}
```

| Sheet Name | Rows (~) | VIN? | Notes |
|---|---|---|---|
| `CARS4PARTS` | 999 | ✅ 96% coverage | Main vehicle inventory |
| `CARSFORSALE` | 48 | ✅ Yes | Whole cars for sale with pricing |
| `ENG/TRA` | unknown | ⚠️ Sparse | Engines and transmissions |
| `ECU` | unknown | ❌ No | ECU/electrical modules |
| `INDIVIDUALPARTS` | unknown | ❌ No | Individual parts with pricing |

> **Sheet name note:** The `ENG TRA` table in AppSheet maps to sheet name `ENG/TRA` in the URL.

### How Discovery Was Made

The inventory page at `/parts` embeds an AppSheet app:
```
https://www.appsheet.com/start/bcd4e61e-096c-4961-9dee-534e93c3e3ab
```

A POST to `https://www.appsheet.com/api/template/{appId}/` (no auth needed for public apps)
returns the full app configuration including the Google Sheets `DocId` under
`Template.AppData.DataSets[*].Source`.

---

## CARS4PARTS Schema

The primary inventory table. Columns:

| Column | Description |
|---|---|
| `ENGVID` | Google Drive link to engine video |
| `TRANSVID` | Google Drive link to transmission video |
| `IMAGES` | AppSheet image path (`CARS4PARTS_Images/{STOCK}.IMAGES.{ts}.jpg`) |
| `FACEBOOK MARKET` | Facebook Marketplace listing URL |
| `ARRIVAL DATE` | Date the vehicle arrived (MM/DD/YY format, not zero-padded) |
| `YEAR MAKE & MODEL` | Combined year/make/model string e.g. `2020 HYUNDAI ELANTRA` |
| `STOCK#` | Stock number (numeric) |
| `SOLDMISSINGDAMGED?` | Status/notes field — see below |
| `ENGINE / MOTOR SIZE & SPECS` | Engine description with VIN digit reference |
| `TRANSMISSION` | Transmission type and details |
| `Color / Body / Codes` | Color and body style |
| `VIN #` | Full 17-character VIN |
| `CP?` | Unknown internal flag |
| `FB?` | Facebook flag |
| `LOCATION` | Yard section (within single lot, e.g. `BACK MID`, `BMW SECTION`) |
| `image2`–`image8` | Additional image paths |

### Status Field (`SOLDMISSINGDAMGED?`)

This field is used for both availability tracking and general notes:
- **Empty** — recently added or fully available
- **Contains "SOLD"** — vehicle is gone (~553 of 999 rows)
- **Other non-empty** — mileage, damage, or inspection notes; vehicle may still be available

The sheet retains **historical records** — sold vehicles are not removed. Filter by
excluding rows where `SOLDMISSINGDAMGED?` contains `SOLD` or `MISSING` to approximate
current inventory.

### VIN Coverage

957 of 999 rows have a VIN. The ~4% without VINs tend to be older/damaged entries.

---

## CARSFORSALE Schema

Whole vehicles for sale with pricing:

| Column | Description |
|---|---|
| `IMAGE`–`IMG6` | AppSheet image paths |
| `YEAR` | Model year |
| `MAKE & MODEL` | Combined make/model |
| `PRICE` | Sale price (string, e.g. `$4,200`) |
| `DESCRIPTION` | Condition notes |
| `MILES?` | Mileage |
| `STOCK` | Stock number |
| `VIDEO` | Google Drive video link |
| `VIN` | Full VIN |
| `COLOR` | Color |
| `TITLE?` | `Y`/`N` — whether title is available |
| `DATE` | Date listed |
| `FB LINK` | Facebook Marketplace link |

---

## Incremental / Recent Arrivals

No dedicated "recent arrivals" page exists on the website.

**Incremental strategy:**  
1. Fetch `CARS4PARTS` CSV sorted by `ARRIVAL DATE` descending (Google Sheets
   does not guarantee order; sort client-side after download).
2. Compare `STOCK#` or `VIN #` against previously seen set.
3. Stop processing when a known stock number is encountered.

The `ARRIVAL DATE` format is inconsistent (`5/17/26`, `05/10/25`, etc.) — normalize
with `dateutil.parser.parse()` before sorting.

---

## Images

AppSheet image paths are relative. Resolve against the AppSheet CDN:
```
https://www.appsheet.com/fsimage.png?appid=bcd4e61e-096c-4961-9dee-534e93c3e3ab
  &datasource=google&filename={IMAGE_PATH_URL_ENCODED}
  &tableprovider=google&userid=1250151
```

Image path example: `CARS4PARTS_Images/90113.IMAGES.140606.jpg`
Resolved: `https://www.appsheet.com/fsimage.png?appid=bcd4e61e-096c-4961-9dee-534e93c3e3ab&datasource=google&filename=CARS4PARTS_Images%2F90113.IMAGES.140606.jpg&tableprovider=google&userid=1250151`

---

## Sample Scrape (Python)

```python
import csv
import requests
from io import StringIO
from datetime import datetime
import dateutil.parser

DOC_ID = "1HySo6ksil-jl6McltcYui6TBC7UvOCMqd754uw4EpOc"

def fetch_sheet(sheet_name: str) -> list[dict]:
    url = f"https://docs.google.com/spreadsheets/d/{DOC_ID}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(StringIO(resp.text))
    return list(reader)

def get_active_inventory() -> list[dict]:
    rows = fetch_sheet("CARS4PARTS")
    active = []
    for row in rows:
        status = row.get("SOLDMISSINGDAMGED?", "").upper()
        if "SOLD" not in status and "MISSING" not in status:
            active.append(row)
    # Sort newest first
    def parse_date(r):
        val = r.get("ARRIVAL DATE", "").strip()
        try:
            return dateutil.parser.parse(val)
        except Exception:
            return datetime.min
    active.sort(key=parse_date, reverse=True)
    return active
```

---

## Notes

- Single yard, single Google Spreadsheet, no pagination.
- AppSheet app is read-only for guests (no auth required to view).
- The Google Sheets export bypasses AppSheet entirely and is the simplest access path.
- Images are served via AppSheet CDN but require the `appid` and `userid=1250151` params — not publicly cacheable without those.
- The `signaler-pa.googleapis.com` Firebase listener used by the AppSheet client is not needed for scraping.
