# Indy U-Pull-It — indyupullit.com

## ⚠️ NO VIN AVAILABLE

The inventory table does **not** expose VINs. The "Engine" column contains a 5–7 digit internal stock number (e.g. `106484`, `99817`). This is NOT a VIN. Approximately 40% of records have no engine/stock number at all. There is no other identifier available to uniquely key a vehicle across runs.

---

## Location

Single location — no multi-yard support.

| Field   | Value |
|---------|-------|
| Name    | Indy U-Pull-It |
| Address | 940 W 16th Street, Indianapolis, IN 46202 |
| Phone   | 317-925-2277 |
| Email (Sales) | sales@indyupullit.com |
| Email (Sell car) | cars@indyupullit.com |
| Hours   | Open Daily: 9:00AM – 6:00PM |
| URL     | https://indyupullit.com |

---

## Inventory Strategy

### Data Source

Single GET request — no pagination, no auth, no AJAX, no tokens required.

```
GET https://indyupullit.com/vehicle-inventory/
```

All inventory is **server-side rendered** into `<table id="vehicles">` on the initial HTML response. WordPress + Elementor site; DataTables (v1.10.24) is initialized client-side with `serverSide: false`. The library paginates DOM rows in-browser — all ~1,255 records are present in the raw HTML.

### Parsing

```python
import requests
from bs4 import BeautifulSoup

resp = requests.get('https://indyupullit.com/vehicle-inventory/', timeout=30)
soup = BeautifulSoup(resp.text, 'lxml')
table = soup.find('table', id='vehicles')
rows = table.find('tbody').find_all('tr')

inventory = []
for row in rows:
    cells = row.find_all('td')
    inventory.append({
        'year':         cells[0].get_text(strip=True),
        'make':         cells[1].get_text(strip=True),
        'model':        cells[2].get_text(strip=True),
        'color':        cells[3].get_text(strip=True),
        'stock_number': cells[4].get_text(strip=True),  # internal ID, NOT a VIN
        'row':          cells[5].get_text(strip=True),
        'arrival_date': cells[6].get_text(strip=True),  # format: MM/DD/YY
    })
```

### Table Columns

| Index | Header       | Notes |
|-------|-------------|-------|
| 0     | Year         | 4-digit year |
| 1     | Make         | UPPERCASE |
| 2     | Model        | UPPERCASE |
| 3     | Color        | UPPERCASE, sometimes blank |
| 4     | Engine       | 5–7 digit stock/inventory number (~60% populated), labeled "Engine" but functions as internal ID |
| 5     | Row          | Yard row number (integer) |
| 6     | Arrival Date | `MM/DD/YY` format; default sort is descending |

### Record Count

~1,255 records observed on 2026-05-19 (single page load confirms total).

---

## Incremental / Recent Arrivals

No dedicated "recent arrivals" page exists. The table is sorted by **Arrival Date descending** by default (`"order": [[6, "desc"]]`). On subsequent runs, parse from the top of the table and stop when an `arrival_date` earlier than the last known date is encountered. Since VINs are unavailable, use a composite key of `(year, make, model, color, row, arrival_date)` for deduplication — note this can produce false duplicates for identical vehicles.

---

## Platform Notes

- WordPress + Elementor Pro
- DataTables 1.10.24 (CDN), client-side mode (`serverSide: false`)
- No admin-ajax.php usage for inventory (Elementor Pro nonce is present but unrelated to inventory)
- No Cloudflare or WAF — plain GET request works from any IP
- No CORS restrictions
