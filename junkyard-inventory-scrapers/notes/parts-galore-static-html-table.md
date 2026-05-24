# Parts Galore — Static HTML Inventory Table

**Site:** https://parts-galore.com/inventory/  
**Scraped:** 2026-05-17  
**Strategy confirmed:** `requests` + BeautifulSoup (no JS rendering needed)

---

## Key Findings

- Full inventory (~1140 rows) is embedded in the initial page HTML as `<table id="alldata">`.
- The client-side JS (`/content/js/inventory-search.js`) only filters/hides rows visually using jQuery — no data is fetched after page load.
- No AJAX calls fire on `$(document).ready`. Selecting a Make triggers only CSS `display` toggling, not any network request.
- A plain `requests.get` with a browser User-Agent returns the full table.

## Attribute Format Gotcha

Row attributes use **single quotes**, not double quotes:
```html
<tr data-make='FORD' data-model='MUSTANG'>
```
Searching for `data-make="` in the raw HTML returns 0 results. Use `data-make='` or parse with BeautifulSoup (which normalises both).

## Table Structure

- Table selector: `table#alldata`
- Rows: `tbody tr` — each row is one vehicle
- Column order (0-indexed): Year | Make | Model | VIN | Color | Yard Date | Row
- VIN is column 3, is always 17 chars, no blanks, all unique per recon
- Yard Date format: `YYYY-MM-DD`
- Row column is the yard aisle number (integer string, e.g. `"78"`)

## Dedup Key

VIN. 1140 rows, 1140 unique VINs, 0 blanks (confirmed via recon).

## How to Spot This Pattern on Other Sites

- Page source contains the full table HTML with data rows (not just an empty `<table>` shell)
- Custom JS file from `/content/js/` or similar (not `/wp-content/plugins/`) that only manipulates DOM visibility
- No `admin-ajax.php`, no `wp-json`, no `fetch`/`XMLHttpRequest` calls on page load
- `<select>` dropdowns are pre-populated with all options; filtering is purely client-side

## robots.txt

No relevant Disallow rules. Yoast block has `Disallow:` (blank — means nothing is disallowed).
