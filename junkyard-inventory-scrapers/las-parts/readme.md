# Lentini Auto Salvage — las-parts.com

**URL:** https://www.las-parts.com/  
**Platform:** URG / Inventory Insite Software (`iis-pro-v2`) — same platform as speedwayap.com  
**Powered by URG** (confirmed in page footer)

---

## Locations

| Yard ID | Name | Address | Phone | Hours |
|---------|------|---------|-------|-------|
| NJ12 | Lentini Auto Salvage — Ringoes, NJ | 130 US-202, Ringoes, NJ 08551 | 800-735-8464 | Mon–Fri 8AM–5PM EST |
| NJ29 | Lentini Auto Salvage — Port Murray, NJ | 89 Brickyard Rd., Port Murray, NJ 07865 | 800-735-8464 | Mon–Fri 8AM–5PM EST |
| II08 | Unknown — not listed on contact page | — | — | — |

> **Note:** The site exposes `var urgid = 'NJ29,II08,NJ12'` (3 yard IDs) but the contact page only documents 2 physical locations. The Port Murray location opened in 2021. `II08` does not map to a standard US state abbreviation and its physical address is unknown — it may be an internal/inactive/parts-only yard. In practice all recent-arrival vehicles observed had CDN paths under `nj12`, suggesting NJ12 is the primary active yard.

---

## VIN Availability

**VINs ARE present** in every vehicle card across all inventory pages.

---

## Scraping Strategy

This site is fully server-side rendered — **no AJAX or browser automation is required** for the inventory crawl. Use plain HTTP GET requests.

### Full Crawl (initial run)

```
1.  GET /parts/makes/
      → Parses all <a href="/parts/{MAKE}"> links with part counts.

2.  For each MAKE:
    GET /parts/{MAKE}/
      → Parses all <a href="/parts/{MAKE}/{MODEL}/"> links.

3.  For each MAKE/MODEL:
    GET /parts/{MAKE}/{MODEL}/
      → Parses all .card-price divs. Each card contains:
          - Stock#   → <div id="{STOCK}"> (the card's HTML id)
          - Year     → <b>Year:</b>
          - Make     → <b>Make/Model :</b>
          - VIN      → <b>Vin :</b>
          - Miles    → <b>Miles :</b>
          - Image    → <img src="https://da8h1v3w8q6n5.cloudfront.net/{yard_id}/images/{STOCK}/{STOCK}_1.jpg">
          - Parts URL → /parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}
```

### Extracting Location per Vehicle

The CDN image URL encodes the yard ID:

```
https://da8h1v3w8q6n5.cloudfront.net/{yard_id}/images/{STOCK}/{STOCK}_1.jpg
```

Extract `{yard_id}` with regex: `cloudfront\.net/([^/]+)/images/`

| CDN prefix | URG Yard ID | Location |
|------------|-------------|----------|
| `nj12` | NJ12 | Ringoes, NJ |
| `nj29` | NJ29 | Port Murray, NJ |
| `ii08` | II08 | Unknown |

> Vehicles with no image will show the placeholder (`/wp-content/plugins/iis-pro-v2/images/no-image-min.webp`) — location cannot be inferred from the image URL in that case. Stock# prefix may serve as an alternate location indicator (observed: `25I` and `26E` both map to `nj12`).

### Incremental / Subsequent Runs

Use the **`/latest-arrivals/`** page as the entry point:

```
GET /latest-arrivals/
  → Returns the 60 most recently added vehicles.
  → Each card includes:
      - Enter Date  → <b>Enter Date:</b> YYYY-MM-DD
      - Stock#, Year, Make/Model, VIN, Miles (same as full crawl)
      - CDN image URL (for yard ID extraction)
  → Stop processing when a Stock# or VIN is already in the database.
  → Fall back to full crawl if no overlap is found in the 60-vehicle window.
```

`/recent-arrivals/` is identical to `/latest-arrivals/` — use either, prefer `/latest-arrivals/` as documented in the iis-pro-v2 platform notes.

---

## HTML Selectors Reference

```python
# Vehicle cards on a /parts/{MAKE}/{MODEL}/ page
cards = soup.select('.card-price')

for card in cards:
    stock   = card['id']
    details = card.select_one('.car-details')
    vin     = re.search(r'Vin\s*:\s*</b>\s*(\S+)', str(details)).group(1)
    year    = re.search(r'Year:\s*</b>\s*(\d{4})', str(details)).group(1)
    miles   = re.search(r'Miles\s*:\s*</b>\s*(\d+)', str(details)).group(1)
    make_model = re.search(r'Make/Model\s*:\s*</b>\s*([^<]+)', str(details)).group(1).strip()
    img_src = card.select_one('img[src*="cloudfront"]')
    yard_id = re.search(r'cloudfront\.net/([^/]+)/images/', img_src['src']).group(1).upper() if img_src else None

# Enter Date (latest-arrivals page only)
    enter_date = re.search(r'Enter Date:\s*</b>\s*([\d-]+)', str(details))
```

---

## URL Structure Summary

```
/parts/makes/                          → all makes with counts
/parts/{MAKE}/                         → models for a make
/parts/{MAKE}/{MODEL}/                 → vehicle cards (VIN, stock, year, miles)
/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}   → individual parts list for a vehicle
/latest-arrivals/                      → 60 most recent vehicles (includes Enter Date)
/recent-arrivals/                      → same as /latest-arrivals/
```

---

## Image CDN

```
Vehicle photo:  https://da8h1v3w8q6n5.cloudfront.net/{yard_id_lower}/images/{STOCK}/{STOCK}_{N}.jpg
```

Multiple images per vehicle (`_1.jpg`, `_2.jpg`, etc.). Missing images return the placeholder from the plugin folder.

---

## Notes

- No authentication or nonce required for any inventory page.  
- No AJAX needed — all data is SSR.  
- The AJAX actions registered by iis-pro-v2 (`getMakesIIS`, `getModelsIIS`, etc.) are present but not needed; AJAX is only used for the search widget on the homepage.  
- The iis-pro-v2 AJAX location actions (`getlocationsIIS`, `getStoresIIS`, etc.) all return `400 / "0"` — location data is not available via AJAX on this site.  
- See [notes/urg-iis-pro-v2-platform.md](../notes/urg-iis-pro-v2-platform.md) for full platform reference and the speedwayap.com reference implementation.
