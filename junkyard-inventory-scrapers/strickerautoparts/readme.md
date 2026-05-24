# Stricker Auto Parts — strickerautoparts.com

## Location

Single location — full-service recycler (not U-Pull).

| Field   | Value |
|---------|-------|
| Name    | Stricker Auto Parts |
| Address | 4955 Benton Road, Batavia, OH 45103 |
| Phone   | 513-732-1152 |
| Hours   | Monday – Friday: 8:30 AM – 4:30 PM EST |
| URL     | https://strickerautoparts.com |

---

## Platform

**URG / Inventory Insite Software — `iis-pro-v2` v4.76**  
Same platform as speedwayap.com and las-parts.com. See notes: [urg-iis-pro-v2-platform.md](../notes/urg-iis-pro-v2-platform.md)

| Config var | Value |
|------------|-------|
| `urgid`    | `AA89` |
| `iispartdir` | `parts` |
| `iisSlug`  | `https://strickerautoparts.com/parts/` |
| `iisajax`  | `https://strickerautoparts.com/wp-admin/admin-ajax.php` |

---

## VIN Availability

**VINs are present on all vehicle cards.** No special handling needed.

---

## Inventory Strategy

All pages are **server-side rendered HTML** — no AJAX, no auth, no nonce required for the crawl path.

### URL Pattern

```
/parts/makes/                              → all makes + part counts (make slugs use underscores)
/parts/{MAKE}/                             → all models for a make + part counts
/parts/{MAKE}/{MODEL}/                     → vehicle cards (Stock, Year, Make/Model, VIN, Miles)
/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}       → individual parts list for a specific vehicle
/latest-arrivals/                          → 60 most recently acquired vehicles, sorted newest first
```

### Full Crawl

1. `GET /parts/makes/` — extract all make slugs from the page (e.g., `CHEVROLET`, `ALFA_ROMEO`). Make slugs use **underscores** for spaces (not hyphens).
2. For each make, `GET /parts/{MAKE}/` — extract all model slugs.
3. For each `(make, model)`, `GET /parts/{MAKE}/{MODEL}/` — extract all vehicle cards.

### Vehicle Card Parsing

Cards live inside `.iis-col-sm-4` divs. Each contains a `.card.card-price` div whose `id` attribute is the **stock number**.

```python
import requests
from bs4 import BeautifulSoup

def scrape_vehicles(make, model):
    url = f"https://strickerautoparts.com/parts/{make}/{model}/"
    soup = BeautifulSoup(requests.get(url, timeout=30).text, "lxml")
    records = []
    for card in soup.select(".iis-col-sm-4 .card.card-price"):
        stock = card.get("id", "").strip()
        rows = card.find_all("tr")
        data = {}
        for row in rows:
            cells = row.find_all("td")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                val = cells[1].get_text(strip=True)
                data[key] = val
        records.append({
            "stock":  stock,
            "year":   data.get("Year"),
            "make":   make,
            "model":  model,
            "vin":    data.get("Vin") or data.get("VIN"),
            "miles":  data.get("Miles"),
        })
    return records
```

### Key Fields (Vehicle Card)

| Field  | Source |
|--------|--------|
| Stock  | `id` attr on `.card.card-price` |
| Year   | table row `Year` |
| Make   | URL slug / table |
| Model  | URL slug / table |
| VIN    | table row `Vin` (17 chars) |
| Miles  | table row `Miles` |

---

## Incremental Monitoring / Recent Arrivals

- **`/latest-arrivals/`** — standard URG SSR page, returns the **60 most recently acquired** vehicles with an `Enter Date` field. Use as the incremental starting point on subsequent runs.
- The site also exposes `/recent-arrivals/` as a WordPress page but `/latest-arrivals/` is the canonical URG plugin page and has the most up-to-date data.
- Stop processing when a stock number or VIN already seen in the database is encountered.

```python
def scrape_latest_arrivals():
    url = "https://strickerautoparts.com/latest-arrivals/"
    soup = BeautifulSoup(requests.get(url, timeout=30).text, "lxml")
    records = []
    for card in soup.select(".iis-col-sm-4 .card.card-price"):
        stock = card.get("id", "").strip()
        rows = card.find_all("tr")
        data = {}
        for row in rows:
            cells = row.find_all("td")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                val = cells[1].get_text(strip=True)
                data[key] = val
        records.append({
            "stock":      stock,
            "year":       data.get("Year"),
            "make":       data.get("Make"),
            "model":      data.get("Model"),
            "vin":        data.get("Vin") or data.get("VIN"),
            "miles":      data.get("Miles"),
            "enter_date": data.get("Enter Date"),
        })
    return records
```

---

## Images

Vehicle thumbnail (lazy-loaded, URL in `data-src`):
```
https://da8h1v3w8q6n5.cloudfront.net/mi34/images/{STOCK}/{STOCK}_1.jpg
```

---

## Notes

- Single-location site — no yard filtering needed.
- Make slugs on this site use underscores (`ALFA_ROMEO`), consistent with other `iis-pro-v2` deployments.
- The nonce (`iisNonce`) is injected inline and valid ~12 hours, but is **not needed** for the SSR crawl path.
- Site also sells parts via WooCommerce and has an eBay store (`stricker_auto`) — these are out of scope.
