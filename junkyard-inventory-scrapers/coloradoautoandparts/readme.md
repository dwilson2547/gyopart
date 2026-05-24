# Colorado Auto & Parts — Inventory Scraper Strategy

**URL:** https://coloradoautoandparts.com/inventory-search/  
**Platform:** WordPress + Colibri Page Builder Pro (no dedicated inventory plugin)

---

> [!CAUTION]
> **VIN IS NOT AVAILABLE.** The inventory table contains no VIN field. Every vehicle record has only: Year, Make, Model, Color, Engine (often blank), Row, and Arrival Date. There is no identifier other than the combination of those fields. Cross-referencing with other systems will not be possible by VIN.

---

## Location

| Field    | Value                                      |
|----------|--------------------------------------------|
| Address  | 2151 W Radcliff Ave, Englewood, CO 80110   |
| Phone    | (303) 761-0112                             |
| Email    | info@coloradoautoandparts.com              |
| Hours    | Mon–Fri 9AM–5PM                            |
| Notes    | Self-service yard, family-owned since 1959 |

Single location only.

---

## Scraping Strategy — SSR Single Table (No Auth Required)

The entire inventory is server-side rendered into one `<table id="vehicles">` on the inventory page. A single GET request returns all records. DataTables (CDN 1.10.24) paginates and sorts entirely client-side — no AJAX, no server-side filtering, no pagination requests needed.

**No auth, no nonce, no cookie, no session required.**

### Single Request

```
GET https://coloradoautoandparts.com/inventory-search/
```

Returns full HTML page. Parse the `<table id="vehicles">` element.

### Record Structure (7 columns)

| Column Index | Field        | Notes                              |
|--------------|--------------|------------------------------------|
| 0            | Year         | 4-digit string                     |
| 1            | Make         | Uppercase (e.g. `CHEVROLET`)       |
| 2            | Model        | Uppercase                          |
| 3            | Color        | Uppercase, may be blank            |
| 4            | Engine       | Almost always blank                |
| 5            | Row          | Yard row number (hidden column)    |
| 6            | Arrival Date | `MM/DD/YY` format (hidden column)  |

Columns 5 and 6 (Row, Arrival Date) are hidden in the browser via `style="display: none;"` but are fully present in the HTML source — no special handling needed server-side.

### Extraction (Python example)

```python
import requests
from bs4 import BeautifulSoup

resp = requests.get('https://coloradoautoandparts.com/inventory-search/', timeout=30)
soup = BeautifulSoup(resp.text, 'html.parser')

# Freshness check
updated_line = soup.find(string=lambda t: t and t.startswith('Updated:'))
# e.g. "Updated: 05/19/26"

table = soup.find('table', id='vehicles')
rows = []
for tr in table.select('tbody tr:not(.child)'):
    cells = tr.find_all('td')
    if len(cells) >= 7:
        rows.append({
            'year':    cells[0].get_text(strip=True),
            'make':    cells[1].get_text(strip=True),
            'model':   cells[2].get_text(strip=True),
            'color':   cells[3].get_text(strip=True),
            'engine':  cells[4].get_text(strip=True),
            'row':     cells[5].get_text(strip=True),
            'arrival': cells[6].get_text(strip=True),
        })
```

> Skip `.child` rows — those are DataTables-generated child rows that duplicate the hidden column data for responsive display. Each parent `<tr>` is followed by a `.child` `<tr>` when viewed in a narrow viewport. In server-side HTML the `.child` rows are pre-rendered as siblings; filter them by class.

---

## Staleness / Incremental Run Strategy

There is no dedicated recent arrivals page and no VIN to deduplicate on. Use these two signals instead:

1. **"Updated:" timestamp** — a plain text node at the top of the inventory page (e.g. `Updated: 05/19/26`). Compare to the last-seen value before parsing. If unchanged, the inventory has not been refreshed since the last run.

2. **Arrival Date field** — the `Arrival Date` hidden column (`MM/DD/YY`) is present on every row and is the default sort key (descending). Sort the fetched rows by arrival date descending and stop processing once you reach dates that were fully captured in the previous run.

Since there is no VIN, deduplication must rely on the composite key `(year, make, model, color, row, arrival_date)`.

---

## Inventory Size

~202 vehicles as of May 2026. 30 unique makes. Single request is sufficient for all inventory with no looping required.

---

## Platform Notes

- WordPress 6.9.4, Colibri Page Builder Pro plugin
- No dedicated junkyard inventory plugin (table is embedded directly in a WP page/block)
- DataTables CDN 1.10.24 with Responsive 2.2.7 extension
- Table ID: `vehicles` (same convention as fenixupull, centralfloridapickandpay, baughmansupullit SSR sites)
- The `Updated:` timestamp preceding the table is rendered as a plain text node by the Colibri page builder — not inside a labelled element; match by content prefix
