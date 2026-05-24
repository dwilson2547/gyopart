# WP Car Manager Plugin — Inventory Pattern

**Applies to:** upullit.jksalvageco.com (confirmed — Eichelberger's U-Pull-It, Spring Grove PA)

---

## Identification

- WordPress plugin: `/wp-content/plugins/wp-car-manager/`
- JS assets: `listings.min.js`, `select2.min.js` — loaded from the plugin path
- Custom post type: `wpcm_vehicle` (not exposed via `/wp-json/wp/v2/` — 404)
- Inline JS object: `var wpcm = {"ajax_url_get_vehicles":"...","ajax_url_get_models":"...","nonce_models":"..."}`
- Form HTML: `<div class="wpcm-vehicle-listings">` with hidden input `#wpcm-listings-nonce`

## Key Findings

- **No VIN** — the plugin does not expose VIN data anywhere (not in listings, detail pages, or REST API)
- Nonce is required but easily extracted from the hidden input on the listing page; no cookies needed
- **`X-Requested-With: XMLHttpRequest` header is mandatory** — without it the API silently returns empty results (no error, no 403)
- Page size is hardcoded at **5 vehicles per page** — small, ~280 requests for ~1,400 vehicles
- Sort by date (`sort=date-desc`) is not in the UI but works as an API param, enabling newest-first crawl
- URL slug (`/vehicle/{slug}/`) is the only unique vehicle identifier
- Detail page fields (condition, engine, transmission, color, body type) require separate GET per vehicle

## API Pattern

```
GET /?wpcm-ajax=get_vehicle_results&nonce={nonce}&page={N}&sort={sort}
```
Nonce from: `<input id="wpcm-listings-nonce" value="...">` on the inventory page.

```
GET /?wpcm-ajax=get_models&nonce={nonce_models}&make={make_id}
```
`nonce_models` from inline `var wpcm` JS object.

Sort values (UI labels differ from API values — `power_kw-asc` = Year old-new, `power_kw-desc` = Year new-old, `date-desc` = newest added first).
