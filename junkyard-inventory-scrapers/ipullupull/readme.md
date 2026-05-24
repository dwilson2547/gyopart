# iPull-uPull Auto Parts — Inventory Scraping Strategy

**Site:** https://ipullupull.com  
**Locations:** 4 yards (Fresno, Pomona, Sacramento, Stockton) — all California

---

## VIN Availability

VIN **IS** available in the CSV exports. Full 17-character VIN is a top-level column in every yard's CSV.

---

## Locations & Contact Info

All location data is available in JSON-LD schema.org (`AutoDealer`) blocks embedded in each location page at `/locations/{city}-ca/`.

| Yard | Address | Phone | Hours |
|------|---------|-------|-------|
| **Fresno** | 2274 East Muscat Avenue, Fresno, CA 93725 | +1 (559) 445-4117 | Mon–Fri 9am–6pm, Sat–Sun 8am–6pm |
| **Pomona** | 1560 East Mission Boulevard, Pomona, CA 91766 | +1 (909) 623-6108 | Mon–Fri 9am–6pm, Sat–Sun 8am–6pm |
| **Sacramento** | 7600 Stockton Boulevard, Sacramento, CA 95823 | +1 (916) 409-3080 | Mon–Fri 9am–6pm (Thu 9:30am), Sat–Sun 8am–6pm |
| **Stockton** | 3151 S. Hwy 99 Frontage Road, Stockton, CA 95215 | +1 (209) 425-0489 | Mon–Fri 9am–6pm (Thu 9:30am), Sat–Sun 8am–6pm |

Last entry daily at 5:30pm across all yards.

---

## Inventory Data Source — CSV Downloads (Preferred)

iPull-uPull publishes a full inventory CSV per yard, updated daily. No authentication, no API scraping required.

| Yard | CSV URL | Current Row Count |
|------|---------|-------------------|
| Fresno | https://ipullupull.com/fresno.csv | ~1,448 vehicles |
| Pomona | https://ipullupull.com/pomona.csv | ~864 vehicles |
| Sacramento | https://ipullupull.com/sacramento.csv | ~1,264 vehicles |
| Stockton | https://ipullupull.com/stockton.csv | ~647 vehicles |

### CSV Schema

```
Date Added, Year, Make, Model, VIN, Stock#, Yard, Row, Fresh Set
```

Note: all columns after `Date Added` have a leading space in the header (e.g., ` VIN`, ` Yard`). Use `str.strip()` when mapping column names.

| Column | Description |
|--------|-------------|
| `Date Added` | ISO date the vehicle arrived in the yard (`YYYY-MM-DD`) |
| `Year` | Model year |
| `Make` | Vehicle make (uppercase) |
| `Model` | Vehicle model (uppercase) |
| `VIN` | Full 17-character VIN |
| `Stock#` | Yard-specific stock number (e.g., `FRE113695`, `POM064657`) |
| `Yard` | Yard name (`Fresno`, `Pomona`, `Sacramento`, `Stockton`) |
| `Row` | Row number in the yard where the vehicle is parked |
| `Fresh Set` | `Yes` if the vehicle was part of the most recent batch set; blank otherwise |

---

## Scraping Strategy

### Full Inventory Sync

```python
import requests
import csv
import io

YARDS = ["fresno", "pomona", "sacramento", "stockton"]

def fetch_yard_inventory(yard: str) -> list[dict]:
    url = f"https://ipullupull.com/{yard}.csv"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    # Strip leading spaces from keys
    return [{k.strip(): v for k, v in row.items()} for row in reader]

all_vehicles = []
for yard in YARDS:
    vehicles = fetch_yard_inventory(yard)
    all_vehicles.extend(vehicles)
```

### Incremental / Recent Arrivals Strategy

The `Fresh Set` column (`Yes` / blank) marks the most recently added batch of vehicles per yard. On subsequent runs:

1. Download all 4 CSVs.
2. Filter rows where `Fresh Set == "Yes"` — these are the newest arrivals.
3. Check each VIN against your existing records.
4. If all `Fresh Set` VINs are already known → the yard has no new inventory since the last full sync.
5. If any `Fresh Set` VINs are new → persist all new rows.

> **Note:** `Fresh Set` appears to mark the latest batch added, not a rolling window. On any given day, ~20–25% of Fresno's inventory is flagged `Yes`. A full re-sync of all CSVs is cheap (4 requests, ~4,000 rows total) so daily full syncs are feasible.

### Suggested Persistence Schema

```sql
CREATE TABLE ipullupull_inventory (
    vin           TEXT NOT NULL,
    stock_number  TEXT NOT NULL,
    yard          TEXT NOT NULL,
    row           INTEGER,
    year          INTEGER,
    make          TEXT,
    model         TEXT,
    date_added    DATE,
    fresh_set     BOOLEAN,
    first_seen    DATE,
    last_seen     DATE,
    PRIMARY KEY (vin, yard)
);
```

---

## Site Technology

- WordPress with a custom plugin (`ipullupull-catalog` — `wp-content/plugins/ipullupull-catalog/`).
- The inventory page at `/inventory-pricing/` renders a filterable table via the plugin, but the **CSV files are the authoritative, simpler data source** — no need to interact with the WordPress plugin API.
- Location detail pages use JSON-LD `AutoDealer` schema for structured address/contact data.

---

## Related Sites

A Canadian sister site exists at https://ipullupullcanada.ca/inventory-pricing/ — same platform, different inventory. Not in scope for this task but likely uses identical CSV export pattern at `/fresno.csv`-equivalent URLs.
