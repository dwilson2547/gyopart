# Tear-A-Part — Inventory Scrape Strategy

**Site:** https://tearapart.com/inventory/  
**Recon Date:** 2026-05-18

---

## VIN Availability

> ✅ **VINs are present** in every inventory record returned by the primary search endpoint. No workaround required.

---

## Locations

| Yard Name        | Store Key       | Client ID | Address                             | Phone          |
|------------------|-----------------|-----------|--------------------------------------|----------------|
| Tear-A-Part SLC  | SALT LAKE CITY  | 1001      | 652 S. Redwood Rd, Salt Lake City, UT 84104 | (801) 886-2345 |
| Tear-A-Part Ogden | OGDEN          | 1080      | 763 W 12th St, Ogden, UT 84404      | (801) 564-6960 |

---

## Platform

Custom WordPress site with a proprietary plugin: `tap-inventory-search-system` (TAP = Tear-A-Part). All data flows through WordPress `admin-ajax.php`.

---

## Authentication

A **WordPress nonce** is required for all data-bearing AJAX actions. Without it the server returns `"test failed!"`.

- The nonce is injected into the page as a JS global on page load:
  ```
  var sif_ajax_object = {
      "sif_ajax_url": "https://tearapart.com/wp-admin/admin-ajax.php",
      "sif_ajax_nonce": "2a94150c40",   ← changes each load, valid ~12 hours
      "sif_plugin_url": "https://tearapart.com/wp-content/plugins/tap-inventory-search-system/"
  };
  ```
- **Extraction:** `GET https://tearapart.com/inventory/` → parse the inline `<script>` for the `sif_ajax_nonce` value.  
  Regex: `"sif_ajax_nonce":"([^"]+)"`

---

## Primary Inventory Endpoint

```
POST https://tearapart.com/wp-admin/admin-ajax.php
Content-Type: application/x-www-form-urlencoded
```

**Parameters:**

| Field                   | Value                        | Notes                            |
|-------------------------|------------------------------|----------------------------------|
| `action`                | `sif_search_products`        | required                         |
| `sif_verify_request`    | `<nonce>`                    | required (12-hour WP nonce)      |
| `sif_form_field_store`  | `SALT LAKE CITY` or `OGDEN`  | required — no "all stores" value |
| `sif_form_field_make`   | `Any`                        | `Any` = all makes                |
| `sif_form_field_model`  | `Any`                        | `Any` = all models               |
| `sorting[key]`          | `iyear`                      | sort column                      |
| `sorting[state]`        | `0`                          | 0 = asc                          |
| `sorting[type]`         | `int`                        | column type                      |

**Response:** JSON

```json
{
  "success": true,
  "message": "<div>824 result(s) found...</div>",
  "products": [ ... ]
}
```

### Response Record Shape

| Field          | Example                      | Notes                                    |
|----------------|------------------------------|------------------------------------------|
| `stocknumber`  | `"STK237517"`                | **Dedup key** — unique per yard          |
| `s3clientid`   | `"1001"`                     | Yard client ID (1001=SLC, 1080=Ogden)   |
| `vin`          | `"JB7FK44E8FP402253"`        | Full 17-char VIN (older cars may be short) |
| `iyear`        | `"1985"`                     | Model year                               |
| `make`         | `"DODGE"`                    |                                          |
| `model`        | `"RAM PICKUP"`               |                                          |
| `color`        | `"WHITE"`                    |                                          |
| `mileage`      | `"818"`                      |                                          |
| `vehicle_row`  | `"18"`                       | Physical aisle row in yard               |
| `yard_date`    | `"05-11-2026"`               | Date entered yard (MM-DD-YYYY)           |
| `yard_in_date` | `"2026-05-11T09:12:41.977"`  | ISO 8601 datetime — use for incremental  |
| `lastupdate`   | `"05/18/2026 00:00:00 AM"`   |                                          |
| `location`     | `"YARD"`                     | `YARD` = active, on-lot                  |
| `istatus`      | `"0"`                        | 0 = in yard                              |
| `hol_year`     | `"1985"`                     | Hollander year                           |
| `hol_mfr_code` | `"CH"`                       | Hollander manufacturer code              |
| `hol_mfr_name` | `"Chrysler"`                 | Hollander manufacturer name              |
| `hol_model`    | `"DODGE 250 PICKUP"`         | Hollander model name                     |
| `reference`    | `"CT35349"`                  | Source reference (often Copart ticket)   |
| `image_url`    | HTML string                  | `<a><img></a>` tag — parse for img src  |
| `yard_name`    | `"TEAR A PART SLC"`          |                                          |
| `yard_city`    | `"SALT LAKE CITY"`           |                                          |
| `yard_state`   | `"UT"`                       |                                          |
| `batch_number` | `"STK237517"`                | Same as stocknumber                      |

---

## Scrape Strategy

### Full Inventory Dump (Initial Run)

Two requests — one per store — are sufficient to capture the entire inventory:

```python
import re, requests

# Step 1: Get a fresh nonce
page = requests.get('https://tearapart.com/inventory/', headers={'User-Agent': 'Mozilla/5.0'})
nonce = re.search(r'"sif_ajax_nonce":"([^"]+)"', page.text).group(1)

ajax_url = 'https://tearapart.com/wp-admin/admin-ajax.php'
base_params = {
    'action': 'sif_search_products',
    'sif_verify_request': nonce,
    'sif_form_field_make': 'Any',
    'sif_form_field_model': 'Any',
    'sorting[key]': 'iyear',
    'sorting[state]': '0',
    'sorting[type]': 'int',
}

all_vehicles = []
for store in ['SALT LAKE CITY', 'OGDEN']:
    resp = requests.post(ajax_url, data={**base_params, 'sif_form_field_store': store})
    data = resp.json()
    if data['success']:
        all_vehicles.extend(data['products'])

# all_vehicles now contains full inventory for both yards
```

**No pagination.** Each call returns the full store inventory in a single response (~800–900 records per store as of recon date).

### Incremental / Delta Updates

The `yard_in_date` field is an ISO 8601 datetime. On subsequent runs:

1. Record the highest `yard_in_date` seen in the previous run.
2. After fetching the full list, filter `yard_in_date > last_run_timestamp` for new arrivals.
3. Dedup on `stocknumber` — if a stocknumber already exists in DB, skip; otherwise insert.

### New Arrivals Pages (Alternative Trigger)

Tear-A-Part has dedicated "just-in" pages that show the last 72 hours:
- https://tearapart.com/just-in-salt-lake-city/
- https://tearapart.com/just-in-ogden/
- https://tearapart.com/new-arrivals/ (both yards combined)

**These pages display Year/Make/Model/Row/Location only — no VIN.** They are rendered via the same `sif` plugin (same nonce system, populated dynamically). They are useful as a human-readable check but are inferior to filtering on `yard_in_date` from the primary API.

---

## Nonce Management

- The nonce is a standard WP nonce, valid for approximately **12 hours**.
- One `GET /inventory/` is all that's needed to obtain a fresh nonce per scrape session.
- No login, cookie, or session required — the nonce is embedded in the public page source.
- The `sif_ajax_nonce` is the same across all `sif_*` AJAX actions on this site.

---

## Other Discovered AJAX Actions (Same Nonce Required)

| Action              | Purpose                                | Returns       |
|---------------------|----------------------------------------|---------------|
| `sif_get_stores`    | List store names as `<option>` HTML    | HTML          |
| `sif_get_locations` | List location names as `<option>` HTML | HTML          |
| `sif_get_makes`     | List all makes as `<option>` HTML      | HTML          |
| `sif_update_models` | List models for a given make           | HTML, needs `make` param |

All of these also require the nonce (`sif_verify_request`).

---

## Second Plugin (gm_inventory_search)

A second WP plugin (`gm_inventory_search`) is also present on the site and has a `get_yard_inventory_data` action. It uses `gm_ajaxurl` with **no nonce in the source code**. However, calling it server-side returns a 502 (backend timeout), suggesting it hits a slower or deprecated backend. **Not recommended as primary strategy.**

---

## robots.txt / ToS Notes

Standard Yoast SEO `robots.txt`. No relevant Disallow rules observed during recon.
