# Arizona Auto Parts — Inventory Scraper Strategy

**URL:** https://arizonaautoparts.com/search-inventory/  
**Platform:** URG IIS Pro v2 (`iis-pro-v2` WP plugin)  
**Yard ID:** `AZ03`

---

## Locations

| Location | Address | Phone | Hours |
|----------|---------|-------|-------|
| Phoenix | 2021 W Buckeye Rd, Phoenix, AZ 85009 | +1 602 253 5111 | Mon–Fri 7:30AM–5:30PM |
| Tucson | 6671 E Littletown Rd, Tucson, AZ 85756 | +1 520 479 1500 | Not listed |

Both locations share a single WordPress site with one unified inventory (single `urgid = 'AZ03'`). There is no per-location filter in the search UI or the SSR inventory pages. Location is not exposed as a field on vehicle cards.

### Location Identification via Stock Suffix

Stock numbers use an alphanumeric format with a trailing letter suffix (e.g. `230358A`, `260844B`). Based on latest-arrivals sampling, the suffix appears to encode location:

| Suffix | Suspected Yard |
|--------|---------------|
| `A` | Phoenix |
| `B` | Tucson |
| `U` | Unknown / unclassified (rare) |

> **This mapping is unconfirmed** — no official documentation exists. Treat suffix as a best-effort location hint; flag `U` suffix records for manual review.

---

## VIN Availability

VIN is present on every vehicle card. No missing-VIN issue.

---

## Scraping Strategy — SSR (No Auth Required)

All inventory data is server-side rendered. No AJAX, no nonce, no session cookie needed for vehicle cards. Standard `GET` requests are sufficient.

### URL Pattern

```
/parts/makes/                              → all makes + vehicle counts
/parts/{MAKE}/                             → all models for a make
/parts/{MAKE}/{MODEL}/                     → vehicle cards for make+model
/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}       → individual parts list for a vehicle
/latest-arrivals/                          → 60 most recent arrivals (with Arrive Date)
```

All paths are absolute under `https://arizonaautoparts.com`.

### Full Crawl Procedure

1. **GET** `/parts/makes/` — parse all `<a href="/parts/{MAKE}">` links (46 makes, ~6,521 total vehicles as of May 2026).
2. For each make, **GET** `/parts/{MAKE}/` — parse all `<a href="/parts/{MAKE}/{MODEL}/">` links.
3. For each model, **GET** `/parts/{MAKE}/{MODEL}/` — parse all `.card.card-price` elements.
4. Extract from each card:
   - **Stock** — card `id` attribute (e.g. `230358A`) and `<b>Stock:</b>` text
   - **Year** — `<b>Year:</b>` text; also in card link URL as last path segment
   - **Make/Model** — `<b>Make/Model :</b>` text
   - **VIN** — `<b>Vin :</b>` text (17-char alphanumeric)
   - **Miles** — `<b>Miles :</b>` text
   - **Location** — infer from stock suffix (A=Phoenix, B=Tucson, U=unknown)

No pagination on model pages — all vehicles for a make/model are returned in a single response.

### Example Card HTML

```html
<div id="230358A" class="card card-price">
  <div class="card-img">
    <a href="//arizonaautoparts.com/parts/CHEVROLET/CAMARO/230358A/2022">
      <img src="https://da8h1v3w8q6n5.cloudfront.net/az03/images/230358A/230358A_392184.jpg">
    </a>
  </div>
  <div class="card-body">
    <div class="car-details">
      <b>Stock:</b> 230358A<br>
      <b>Year:</b> 2022<br>
      <b>Make/Model :</b> CHEVROLET CAMARO<br>
      <b>Vin :</b> 1G1FK1R66N0101478<br>
      <b>Miles :</b> 0<br>
    </div>
    <a href="//arizonaautoparts.com/parts/CHEVROLET/CAMARO/230358A/2022" ...>See Parts</a>
  </div>
</div>
```

### Estimated Request Count

| Step | Count |
|------|-------|
| Makes page | 1 |
| Make pages (46 makes) | 46 |
| Model pages (~8 avg models/make) | ~370 |
| **Total** | **~417 requests** |

No per-page row cap observed (unlike the fenixupull variant with 50-row limit). Entire make/model result set is returned in one response.

---

## Image CDN

```
https://da8h1v3w8q6n5.cloudfront.net/az03/images/{STOCK}/{STOCK}_{N}.jpg
```

Images lazy-loaded — actual URL is in both `src` and `data-src` attributes on this site.

---

## Recent Arrivals / Incremental Updates

`/latest-arrivals/` returns the 60 most recently added vehicles sorted by arrive date descending. Each card includes an `Arrive Date: YYYY-MM-DD` field (not `Purchase Date` as on other URG sites).

**Incremental strategy:** On subsequent runs, fetch `/latest-arrivals/`, collect VINs, and stop processing when all VINs on the page are already known. If 60 is insufficient (high-volume yard), fall back to a full crawl sorted by comparing known stock numbers against what's found on model pages.

---

## IIS AJAX Actions (Admin-Ajax — Not Needed for Vehicle Inventory)

The site exposes `https://arizonaautoparts.com/wp-admin/admin-ajax.php` with the standard URG AJAX actions (see `urg-iis-pro-v2-platform.md` notes). These are not required for a full vehicle crawl since the SSR pages provide everything.

Nonce extraction if needed:
```python
import re, requests
html = requests.get('https://arizonaautoparts.com/search-inventory/').text
nonce = re.search(r"iisNonce\s*=\s*'([^']+)'", html).group(1)
```

---

## Platform Notes

- Confirmed URG IIS Pro v2 via `iis-pro-v2` plugin path in page source
- Plugin version: `4.76`
- WooCommerce also loaded (for parts e-commerce) — does not affect inventory scraping
- `iisajaxflow` endpoint present at `/ajaxflow` — purpose unclear, not needed
- Footer: "Powered by URG Web Services" (different wording from "Powered by URG" checked in notes)
- Stock numbers are **alphanumeric** (e.g. `230358A`) — differs from numeric-only stock IDs seen on other URG sites
