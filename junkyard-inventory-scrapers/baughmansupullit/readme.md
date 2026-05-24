# Baughman's U-Pull-It — baughmansupullit.com

## ⚠️ NO VIN AVAILABLE

The inventory table does **not** expose VINs. The only unique identifier is an internal **stock number** (`STK######`, e.g. `STK038518`). This is NOT a VIN. Use the stock number as the deduplication key across runs.

---

## Location

Single location — no multi-yard support.

| Field   | Value |
|---------|-------|
| Name    | Baughman's U-Pull-It |
| Address | 441 Eberts Lane, York, PA 17403 |
| Phone   | 717-846-3944 |
| Hours   | Mon–Sat: 9:00 AM – 5:00 PM (must enter yard before 4:30 PM) |
| URL     | https://baughmansupullit.com |

---

## Inventory Strategy

### Data Source

All inventory is **server-side rendered**. No AJAX, no auth, no tokens required. The form submits as a plain `GET` request to the inventory page.

```
GET https://baughmansupullit.com/inventory/?make={MAKE}&model=
```

- Returns full HTML with a `<table>` of matching vehicles.
- **No pagination** — all records for a make are returned in a single response.
- Requesting with an empty/invalid make returns only the header row (no results).
- Must enumerate by make — there is no "all inventory" endpoint.

### Make List (37 total)

```
ACURA, AUDI, BMW, BUICK, CADILLAC, CHEVROLET, CHRYSLER, DODGE, FORD,
FREIGHTLINER, GEO, GMC, HONDA, HYUNDAI, INFINITI, ISUZU, JEEP, KIA,
LAND ROVER, LEXUS, LINCOLN, MAZDA, MERCEDES-BENZ, MERCURY, MINI,
MITSUBISHI, NISSAN, OLDSMOBILE, PLYMOUTH, PONTIAC, SATURN, SCION,
SUBARU, SUZUKI, TOYOTA, VOLKSWAGEN, VOLVO
```

These are hard-coded in the select dropdown on the page and can also be scraped dynamically from `<select id="makeSelect"> option` elements.

### Parsing

```python
import requests
from bs4 import BeautifulSoup

MAKES = [
    "ACURA", "AUDI", "BMW", "BUICK", "CADILLAC", "CHEVROLET", "CHRYSLER",
    "DODGE", "FORD", "FREIGHTLINER", "GEO", "GMC", "HONDA", "HYUNDAI",
    "INFINITI", "ISUZU", "JEEP", "KIA", "LAND ROVER", "LEXUS", "LINCOLN",
    "MAZDA", "MERCEDES-BENZ", "MERCURY", "MINI", "MITSUBISHI", "NISSAN",
    "OLDSMOBILE", "PLYMOUTH", "PONTIAC", "SATURN", "SCION", "SUBARU",
    "SUZUKI", "TOYOTA", "VOLKSWAGEN", "VOLVO",
]

BASE_URL = "https://baughmansupullit.com/inventory/"

session = requests.Session()
inventory = []

for make in MAKES:
    resp = session.get(BASE_URL, params={"make": make, "model": ""}, timeout=30)
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table")
    if not table:
        continue
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        # Stock number is the text content of the first image column td
        # before the <a> tag (style="font-size: 0px;")
        stock_td = cells[6]
        stock_number = stock_td.get_text(strip=True).split()[0] if stock_td.get_text(strip=True) else ""
        inventory.append({
            "year":         cells[0].get_text(strip=True),
            "make":         cells[1].get_text(strip=True),
            "model":        cells[2].get_text(strip=True),
            "color":        cells[3].get_text(strip=True),
            "row":          cells[4].get_text(strip=True),
            "arrival_date": cells[5].get_text(strip=True),  # format: MM/DD/YY
            "stock_number": stock_number,                    # e.g. STK038518 — NOT a VIN
        })
```

### Table Columns

| Index | `data-label` Attribute | Notes |
|-------|------------------------|-------|
| 0     | `Year`                 | 4-digit year |
| 1     | `Make`                 | UPPERCASE |
| 2     | `Model`                | UPPERCASE |
| 3     | `Color`                | UPPERCASE, sometimes blank |
| 4     | `Row`                  | Yard row number (e.g. `105`) |
| 5     | `Yard Date`            | `MM/DD/YY` format |
| 6–9   | _(image columns)_      | `style="font-size: 0px;"` — contains the stock number as leading text, followed by an `<a><img></a>` link |

The stock number is extracted from cell index 6 (first image column). The text content before the `<a>` tag is `STK######` followed by whitespace. Using `.get_text(strip=True).split()[0]` reliably extracts it.

### Image URL Pattern

Each vehicle has up to 4 photos:

```
https://baughmansupullit.com/inventory-photos/{STOCK}.JPG
https://baughmansupullit.com/inventory-photos/{STOCK}A.JPG
https://baughmansupullit.com/inventory-photos/{STOCK}B.JPG
https://baughmansupullit.com/inventory-photos/{STOCK}C.JPG
```

Images may or may not exist for each suffix. The `<img src>` in the HTML only contains the path if a photo was uploaded.

### Approximate Inventory Size

~105 Honda vehicles observed on 2026-05-19; Ford yielded ~114. Expect 50–150 vehicles per popular make, fewer for rare makes. Total active inventory estimated at 500–800 vehicles.

---

## Incremental / Recent Arrivals

```
GET https://baughmansupullit.com/inventory/new-arrivals/
```

- Returns all vehicles added in the **last 7 days** — SSR HTML, no auth.
- `<table id="vehicles" class="display">` — DataTables with `serverSide: false`; all rows in the initial HTML response (no JS execution needed).
- Columns: `Arrival Date`, `Year`, `Make`, `Model`, `Color`, `Stock Number`, `Row`.
- **Strategy:** On subsequent runs, fetch `/inventory/new-arrivals/` first. If every stock number on the page was seen in a previous full crawl, the full inventory has not changed. If new stock numbers appear, do a full crawl to sync.
- No VIN on this page either — stock number is still the only identifier.

```python
resp = session.get("https://baughmansupullit.com/inventory/new-arrivals/", timeout=30)
soup = BeautifulSoup(resp.text, "lxml")
table = soup.find("table", id="vehicles")
for row in table.find("tbody").find_all("tr"):
    cells = row.find_all("td")
    record = {
        "arrival_date": cells[0].get_text(strip=True),
        "year":         cells[1].get_text(strip=True),
        "make":         cells[2].get_text(strip=True),
        "model":        cells[3].get_text(strip=True),
        "color":        cells[4].get_text(strip=True),
        "stock_number": cells[5].get_text(strip=True),
        "row":          cells[6].get_text(strip=True),
    }
```

---

## Rate Limiting / Access

- No Cloudflare challenge, no bot protection detected.
- Standard `requests.Session()` with a browser-like `User-Agent` works.
- 37 GET requests to enumerate all makes — lightweight crawl.
