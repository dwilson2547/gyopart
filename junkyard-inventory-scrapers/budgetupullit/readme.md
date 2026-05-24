# Budget U-Pull-It — budgetupullit.com

## Location

Single location — no multi-yard support.

| Field   | Value |
|---------|-------|
| Name    | Budget U-Pull-It |
| Address | 881 South 9th Street, Winter Garden, FL 34787 |
| Phone   | 407-656-4707 |
| Email   | sales@budgetupullit.com |
| Hours   | Open 7 days a week, 8:00 AM – 5:00 PM (Yard closes at 4:30 PM) |
| URL     | https://budgetupullit.com |

---

## Inventory Strategy

### Data Source

All inventory is **server-side rendered HTML**. No AJAX, no auth, no nonces required. The form on `/current-inventory/` and `/search-vehicles/` submits as a plain `GET` request.

```
GET https://budgetupullit.com/current-inventory/?make={MAKE}&model=
```

- Returns a full HTML page containing a `<table class="resultsTable">` with matching vehicles.
- **No pagination** — all records for a given make are returned in a single response (tested: 264 Chevrolet records on one page).
- Requesting with an empty or invalid `make` returns only the header row — no results.
- There is no "get all inventory" endpoint; must enumerate by make.

### Make List (39 total)

Scraped dynamically from `<select id="makeSelect">` on the page, or use this hard-coded list:

```
ACURA, ALFA ROMEO, AUDI, BMW, BUICK, CADILLAC, CHEVROLET, CHRYSLER,
DODGE, FIAT, FORD, GEO, GMC, HONDA, HYUNDAI, INFINITI, JAGUAR, JEEP,
KIA, LEXUS, LINCOLN, MAZDA, MERCEDES-BENZ, MERCURY, MINI, MITSUBISHI,
NISSAN, OLDSMOBILE, PONTIAC, PORSCHE, RAM, SATURN, SCION, SMART,
SUBARU, SUZUKI, TOYOTA, VOLKSWAGEN, VOLVO
```

A full make → model mapping is also embedded as a JS variable (`modelMap`) in the page source at `/search-vehicles/`. Not required for full scraping since make-level queries return all models for that make.

### Table Columns

The results table (`<table class="resultsTable" style="width:100%">`) has these columns:

| Index | `data-label` Attribute | Notes |
|-------|------------------------|-------|
| 0     | `\nYear` (or `Year`)   | 4-digit year |
| 1     | `\nMake`               | UPPERCASE |
| 2     | `\nModel`              | UPPERCASE |
| 3     | `\nStock#`             | Format: `STK#####`, e.g. `STK82289` |
| 4     | `\nRow`                | Row number in yard |
| 5     | `\nVin`                | **Full 17-char VIN** |
| 6     | `\nDate`               | Yard arrival date, format `MM.DD.YY` |

> Note: `data-label` attribute values have a leading newline (`\n`) — strip whitespace when reading.

### Parsing

```python
import requests
from bs4 import BeautifulSoup

MAKES = [
    "ACURA", "ALFA ROMEO", "AUDI", "BMW", "BUICK", "CADILLAC", "CHEVROLET",
    "CHRYSLER", "DODGE", "FIAT", "FORD", "GEO", "GMC", "HONDA", "HYUNDAI",
    "INFINITI", "JAGUAR", "JEEP", "KIA", "LEXUS", "LINCOLN", "MAZDA",
    "MERCEDES-BENZ", "MERCURY", "MINI", "MITSUBISHI", "NISSAN", "OLDSMOBILE",
    "PONTIAC", "PORSCHE", "RAM", "SATURN", "SCION", "SMART", "SUBARU",
    "SUZUKI", "TOYOTA", "VOLKSWAGEN", "VOLVO",
]

BASE_URL = "https://budgetupullit.com/current-inventory/"

session = requests.Session()
inventory = []

for make in MAKES:
    resp = session.get(BASE_URL, params={"make": make, "model": ""}, timeout=30)
    soup = BeautifulSoup(resp.text, "lxml")

    # The results table is the second .resultsTable on the page
    tables = soup.find_all("table", class_="resultsTable")
    results_table = tables[-1] if tables else None
    if not results_table:
        continue

    for row in results_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        inventory.append({
            "year":        cells[0].get_text(strip=True),
            "make":        cells[1].get_text(strip=True),
            "model":       cells[2].get_text(strip=True),
            "stock_number": cells[3].get_text(strip=True),   # e.g. STK82289
            "row":         cells[4].get_text(strip=True),
            "vin":         cells[5].get_text(strip=True),    # full 17-char VIN
            "yard_date":   cells[6].get_text(strip=True),    # MM.DD.YY
        })
```

---

## Recent Arrivals / Incremental Runs

A dedicated **New Arrivals** page exists:

```
GET https://budgetupullit.com/new-arrivals/
```

- Returns a table with columns: Year, Make, Model, Vehicle Row, VIN, Arrival Date, Image.
- Arrival Date format: `MM/DD/YY` (different from the inventory date format `MM.DD.YY`).
- **No date filter** — shows a static recent window (exact lookback window unknown; observed entries spanning several weeks).
- **VINs are present** — can be used for deduplication.

### Incremental Run Strategy

1. Fetch `/new-arrivals/` and extract all VINs.
2. Compare against the set of VINs already in the database.
3. If **all** VINs on the new-arrivals page have been seen before, the yard has not added new vehicles since the last full run — **stop early**.
4. If any VINs are new, run the full per-make scan to capture the complete current inventory state.

---

## Site Notes

- WordPress site using the `car-repair-services` theme.
- `MyAjax` / `admin-ajax.php` references are from the `advanced-iframe` plugin and cookie-notice plugin — **not used for inventory**. The inventory is rendered entirely server-side in PHP.
- No Cloudflare challenge or bot protection observed; plain `requests` with no special headers is sufficient.
- Single yard; no location ID or yard selector needed.
