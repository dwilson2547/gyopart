# Eichelberger's U-Pull-It — JK Salvage Co
**Site:** https://upullit.jksalvageco.com/cars/

---

> ⚠️ **NO VIN AVAILABLE**
> The WP Car Manager plugin used by this site does not expose VIN anywhere — not on listing pages, individual vehicle pages, REST API, or any discovered endpoint. The URL slug (e.g. `/vehicle/2011-nissan-murano-2/`) is the only unique identifier per vehicle.

---

## Location

Single location:

| Field    | Value                                      |
|----------|--------------------------------------------|
| Name     | Eichelberger's U-Pull-It                   |
| Address  | 1381 Sunnyside Rd, Spring Grove, PA 17362  |
| Phone    | 717-225-5610                               |
| Email    | Eichelbergers@jksalvageco.com              |
| Hours    | Mon–Fri 8AM–4PM, Sat 8AM–2PM, Sun Closed  |

---

## Platform

**WordPress** with the [WP Car Manager](https://wordpress.org/plugins/wp-car-manager/) plugin (`/wp-content/plugins/wp-car-manager/`), Divi theme.

---

## Inventory API

### Nonce

A WP nonce is required. Extract it from the `/cars/` page before each run:

```python
import re, requests

resp = requests.get("https://upullit.jksalvageco.com/cars/")
nonce = re.search(r'id="wpcm-listings-nonce"[^>]*value="([^"]+)"', resp.text).group(1)
```

The nonce is valid ~12 hours. Refresh at the start of each run.

### Get Vehicle Listings

```
GET https://upullit.jksalvageco.com/?wpcm-ajax=get_vehicle_results
```

**Required header:** `X-Requested-With: XMLHttpRequest`
(Without this header the API returns empty results, not a 403.)

**Parameters:**

| Param        | Required | Notes                                       |
|--------------|----------|---------------------------------------------|
| `nonce`      | Yes      | From `#wpcm-listings-nonce` hidden input    |
| `page`       | Yes      | 1-indexed                                   |
| `sort`       | Yes      | See sort values below                       |
| `filter_make`| No       | Make ID integer (from make select options)  |
| `filter_model`| No      | Model ID integer (from model select)        |
| `filter_year`| No       | Year integer                                |

**Sort values:**

| API value      | UI label           |
|----------------|--------------------|
| `power_kw-asc` | Year (old → new)   |
| `power_kw-desc`| Year (new → old)   |
| `mileage-asc`  | Mileage (low-high) |
| `mileage-desc` | Mileage (high-low) |
| `date-desc`    | Newest added first (not shown in UI but works) |
| `price-asc`    | Default page sort  |

**Response:** JSON `{ "listings": "<HTML>", "pagination": "<HTML>" | null }`

**Page size:** 5 vehicles per page  
**Total inventory:** ~278 pages → ~1,390 vehicles

### Get Models (for filtering)

```
GET https://upullit.jksalvageco.com/?wpcm-ajax=get_models&nonce={nonce_models}&make={make_id}
```

`nonce_models` is in the inline `var wpcm = {...}` JS object on the page.  
Returns a JSON array: `[{"id": 123, "name": "Civic"}, ...]`

---

## Data Fields Per Vehicle

Extracted from the listings HTML and individual vehicle pages:

| Field        | Source               | Notes                              |
|--------------|----------------------|------------------------------------|
| Year         | `<h3>` title         |                                    |
| Make         | `<h3>` title         |                                    |
| Model        | `<h3>` title         |                                    |
| Mileage (raw)| `<p>` in description | Actual number (e.g. `170993`)      |
| Mileage (K)  | Meta `<li>`          | Rounded to thousands (e.g. `171 miles`) |
| Posted date  | Meta `<li>`          | Format `MM-YYYY` (e.g. `04-2026`)  |
| Vehicle URL  | `<a href>`           | Unique slug, serves as record ID   |
| Condition    | Detail page only     | e.g. `No Damage`                   |
| Transmission | Detail page only     | e.g. `Automatic`                   |
| Engine       | Detail page only     | e.g. `3.5-?`                       |
| Color        | Detail page only     | e.g. `white`                       |
| Body type    | Detail page only     | e.g. `suv`                         |
| VIN          | **Not available**    | Not stored or exposed by plugin    |

---

## Full Scrape Strategy

```python
import re, requests
from bs4 import BeautifulSoup

BASE_URL = "https://upullit.jksalvageco.com"
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_URL}/cars/",
}

# 1. Fetch fresh nonce
resp = requests.get(f"{BASE_URL}/cars/")
nonce = re.search(r'id="wpcm-listings-nonce"[^>]*value="([^"]+)"', resp.text).group(1)

# 2. Page through all results
page = 1
vehicles = []
while True:
    r = requests.get(
        f"{BASE_URL}/?wpcm-ajax=get_vehicle_results",
        params={"nonce": nonce, "page": page, "sort": "power_kw-asc"},
        headers=HEADERS,
    )
    data = r.json()
    soup = BeautifulSoup(data["listings"], "html.parser")
    items = soup.select("li.wpcm-listings-item")
    if not items or "wpcm-no-results" in data["listings"]:
        break
    for item in items:
        a = item.find("a")
        url = a["href"] if a else ""
        title = item.select_one(".wpcm-title")
        mileage_raw = item.select_one(".wpcm-listings-item-description p")
        posted = None
        for li in item.select(".wpcm-listings-item-meta li"):
            if "Posted:" in li.text:
                posted = li.text.replace("Posted:", "").strip()
        vehicles.append({
            "url": url,
            "title": title.text.strip() if title else "",
            "mileage_raw": mileage_raw.text.strip() if mileage_raw else "",
            "posted": posted,
        })
    if data.get("pagination") is None:
        break
    page += 1

# 3. Parse year/make/model from title: "2011 Nissan Murano"
for v in vehicles:
    parts = v["title"].split(" ", 2)
    v["year"] = parts[0] if len(parts) > 0 else ""
    v["make"] = parts[1] if len(parts) > 1 else ""
    v["model"] = parts[2] if len(parts) > 2 else ""
```

---

## Incremental / Recent Arrivals Strategy

No dedicated recent-arrivals page exists. Use `sort=date-desc` to walk newest entries first and stop when a known URL slug is encountered:

```python
# On subsequent runs, load a set of previously-seen URL slugs
seen_slugs = load_seen_slugs()  # from DB or file

page = 1
new_vehicles = []
while True:
    r = requests.get(
        f"{BASE_URL}/?wpcm-ajax=get_vehicle_results",
        params={"nonce": nonce, "page": page, "sort": "date-desc"},
        headers=HEADERS,
    )
    data = r.json()
    items = BeautifulSoup(data["listings"], "html.parser").select("li.wpcm-listings-item")
    stop = False
    for item in items:
        a = item.find("a")
        slug = a["href"].rstrip("/").split("/")[-1] if a else ""
        if slug in seen_slugs:
            stop = True
            break
        new_vehicles.append(...)  # parse as above
    if stop or data.get("pagination") is None:
        break
    page += 1
```

---

## Notes

- **Single location** — no multi-yard logic needed.
- **Nonce required** but trivially extracted; no cookies or session needed.
- `X-Requested-With: XMLHttpRequest` header is mandatory; omitting it causes the API to return empty results silently (not a 403).
- Page size is hardcoded at 5 — small, so ~280 requests for a full crawl.
- The `<p>` in each listing card is the raw mileage integer; the meta `<li>` rounds it to thousands.
- Detail page fetch is not necessary for the primary fields; only needed if condition/transmission/engine/color/body-type are required.
- No VIN anywhere — URL slug is the only stable per-vehicle key.
