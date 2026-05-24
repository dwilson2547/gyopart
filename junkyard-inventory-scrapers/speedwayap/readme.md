# Speedway Auto Parts – Scraping Strategy

**URL:** https://speedwayap.com/search-inventory/  
**Platform:** URG (Used Recycled & Graded) / Inventory Insite Software (`iis-pro-v2` v4.76)  
**Type:** Traditional auto recycler (not self-service/U-Pull). Parts pulled by staff.  
**Yard ID (urgid):** `IL22`

---

## ✅ VINs ARE Available

VINs are present at two levels:
1. **Vehicle listing pages** – each vehicle card shows `Vin: {17-char VIN}`
2. **Individual part records** – each part shows `VIN: {17-char VIN}` of the donor vehicle

No special auth or AJAX calls needed – VINs are in the server-side rendered HTML.

---

## Location

Single location:

| Field    | Value                               |
|----------|-------------------------------------|
| Name     | Speedway Auto Parts, LTD            |
| Address  | 1301 Herkimer St, Joliet, IL 60432  |
| Phone    | 815-726-0666                        |
| Hours    | Mon–Fri 8AM–5PM CST. Sat/Sun closed |

The site header says "Chicago, IL \| Joliet, IL" but is marketing copy only – Joliet is in the Chicago metro. Only one physical location confirmed via contact page and schema.org structured data.

---

## Data Architecture

The inventory is organized in a 4-level hierarchy, all server-side rendered (no AJAX needed):

```
/parts/makes/
  └── /parts/{MAKE}/
        └── /parts/{MAKE}/{MODEL}/              ← vehicle cards here (VIN, stock#, miles)
              └── /parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}   ← individual parts here
```

### Vehicle Card Fields (`/parts/{MAKE}/{MODEL}/`)

Each vehicle card (`.iis-col-sm-4`) contains:

| Field      | Example              |
|------------|----------------------|
| Stock      | `CB3310`             |
| Year       | `2024`               |
| Make/Model | `CHEVROLET EQUINOX`  |
| Vin        | `3GNAXSEG9RL294393`  |
| Miles      | `8000`               |

HTML card `id` attribute matches stock number (e.g. `<div id="CB3310">`).  
"See Parts" link: `//speedwayap.com/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}`

### Individual Part Fields (`/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}`)

Each part row in the `<table id="large">` contains:

| Field        | Example                                          |
|--------------|--------------------------------------------------|
| Part Type    | `CARRIER ASSEMBLY`                               |
| Part Numbers | `84345027 84467601 84633471` (OEM/Hollander)     |
| Details      | `1.5T,AOD,GNA,8MI`                               |
| Stock        | `CB3310`                                         |
| Tag          | `R02872084`                                      |
| VIN          | `3GNAXSEG9RL294393`                              |
| SKU          | `AA242872084`                                    |
| Part Grade   | `A`                                              |
| Price        | `$150.00`                                        |

---

## Scraping Strategy

Since all data is server-side rendered HTML, no AJAX or auth tokens are needed for the core crawl.

### Full Inventory Crawl (Vehicle Level)

```
1. GET https://speedwayap.com/parts/makes/
   → Parse make list: text like "CHEVROLET 433" (make + part count)
   → Selector: page body text / anchors linking to /parts/{MAKE}/

2. For each MAKE:
   GET https://speedwayap.com/parts/{MAKE}/
   → Parse model list: "EQUINOX 78", "MALIBU 62", etc.
   → No pagination

3. For each MAKE + MODEL:
   GET https://speedwayap.com/parts/{MAKE}/{MODEL}/
   → Parse vehicle cards: div.iis-col-sm-4 > div.card-price
   → Selector: div[id^="CB"], div[id^="M"], etc. (card id = stock#)
   → Extract: Stock, Year, Make/Model, Vin, Miles
   → No pagination observed (78 parts = parts count not vehicle count)

4. Optional – per-vehicle parts detail:
   GET https://speedwayap.com/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}
   → Parse <table id="large"> rows
   → Extract: Part Type, Part Numbers, Details, Stock, Tag, VIN, SKU, Grade, Price
```

### Incremental Monitoring via Latest Arrivals

`https://speedwayap.com/latest-arrivals/` shows the most recent **60 acquisitions**, sorted newest-first.

Each card includes a `Purchase Date` field (e.g. `2026-05-15`) not present on regular model pages.

**Suggested incremental strategy:**
- On each run, fetch `/latest-arrivals/`
- Extract vehicles; stop processing when you hit a stock number or VIN already in the database
- Fall back to full crawl if no known stock/VIN found within the 60 entries

---

## Image URLs

Two patterns depending on context:

| Context        | Pattern                                                                 |
|----------------|-------------------------------------------------------------------------|
| Vehicle thumbnail | `https://da8h1v3w8q6n5.cloudfront.net/mi34/images/{STOCK}/{STOCK}_1.jpg` |
| Part photo     | `https://da8h1v3w8q6n5.cloudfront.net/mi34/inventory/{STOCK}/{TAG}_{N}.jpg` |

Lazy-loaded via `data-src` attribute (img has placeholder `no-image-min.webp` in `src`).

---

## AJAX Actions (Optional / Not Required)

The URG plugin registers these AJAX actions at `/wp-admin/admin-ajax.php`. These are used by the search widget on `/search-inventory/` and are not needed for a parts crawl, but could be used to enumerate inventory by part type.

**Nonce required for all calls:**  
- Variable: `iisNonce` injected inline in page HTML  
- Extraction regex: `/iisNonce\s*=\s*'([^']+)'/`  
- Changes periodically; extract fresh on each session from any page that loads the plugin

| Action                 | Required Params          | Returns                                |
|------------------------|--------------------------|----------------------------------------|
| `getMakesIIS`          | `year`                   | `{makes:[{make, value},...]}`          |
| `getModelsIIS`         | `year`, `make`           | `{models:[{model, value},...]}`        |
| `getpartCategoriesIIS` | _(none)_                 | `{categories:[...]}`                   |
| `getpartTypesIISModal` | `category`               | `{parts:[...]}`                        |
| `getVerticalIIS`       | _(none)_                 | `{vertical:"<html year dropdown>"}` |
| `getprefilldataIIS`    | `iisYear`, `iisMake`     | prefill data for search form           |

All actions can be called without authentication (no cookie/nonce needed for GET-style calls, though the widget sends nonce for POST).

---

## Parts Search URL (Not recommended for crawl)

The site supports part-type search URLs:

```
https://speedwayap.com/parts/{MAKE}/{MODEL}/{PART_TYPE}/{YEAR}/?k=1
```

Returns "PART NOT FOUND" when no matching parts are in stock. Not useful for inventory discovery – use the hierarchy crawl instead.

---

## Notes

- The `iis-pro-v2` plugin is a WordPress plugin by URG. See [`notes/urg-iis-pro-v2-platform.md`](../notes/urg-iis-pro-v2-platform.md) for platform-level patterns that apply to any URG-powered yard.
- Stock number prefixes observed: `CB` (e.g. `CB3310`), `M` (e.g. `M26293`) – may indicate different vehicle batches or purchase sources; both appear in the same single-location inventory.
- Inventory size at time of analysis: ~3,337 parts across 44 makes.
