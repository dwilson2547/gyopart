# WordPress Junkyard Inventory Sites — Recon Patterns

**Applies to:** pullnsave.com (confirmed), likely other WP-based junkyard chains

---

## How to Find the API Fast

1. **Check page source for `admin-ajax.php` references** — WordPress AJAX is the primary data transport for WP-based junkyard sites. All meaningful data calls go through `/wp-admin/admin-ajax.php` via POST with an `action` param.

2. **Load custom plugin JS files** — In page source, look for `<script src>` tags pointing to `/wp-content/plugins/`. These contain the full list of AJAX actions the site uses, the POST params for each, and any direct backend API URLs embedded as JS variables.
   - On Pull-N-Save: `pns-vehicle-search/front-end/assets/js/pns-inventory-functions.js` revealed all actions and a direct backend URL (`app.pullnsaveapp.com/v1/Vehicles/Search`) embedded in a `var pns_inventory_sf_ajax` object.

3. **Check inline `<script>` blocks for localized JS vars** — WordPress uses `wp_localize_script()` to inject config objects into the page. These often contain: the AJAX URL, a nonce, and sometimes a direct API base URL. Pattern: `var something_ajax = {"url":"...","nonce":"...","apiurl":"..."}`.

4. **Try the legacy plugin JS too** — WP sites frequently layer new plugins on top of old ones. The old plugin's JS often uses AJAX actions with no nonce requirement and is easier to call server-side.

---

## WordPress AJAX Action Discovery Pattern

Once you have the plugin JS file, extract all `action` values:
```
grep -oP '"action"\s*:\s*"\K[^"]+' plugin.js
```

Common pattern for a junkyard site (Pull-N-Save had all of these):
- `getStores` — no auth, returns locations JSON
- `getMakes` — no auth, returns HTML options (all makes in DB)
- `getModels` — no auth, needs `Make` param
- `getYears` — no auth, needs `Make` and optionally `Model`
- `getVehicles` — **primary scrape target**, no auth, returns HTML table
- `pns_get_inventory_assets` — newer JSON version, **requires nonce**

**Test each action without auth first** — legacy actions often work without a nonce even if newer ones don't.

---

## Server-Side vs. Browser Access

| Endpoint | Server-side (curl/requests) | Browser |
|---|---|---|
| `admin-ajax.php` legacy actions | ✅ Works | ✅ Works |
| `admin-ajax.php` newer actions (nonce) | ⚠️ 403 from WAF | ✅ Works |
| Direct mobile app API (if found) | ✅ Works (no CORS) | ❌ CORS blocked |

**Key insight:** A direct mobile/app API URL embedded in the site's JS (e.g., `app.pullnsaveapp.com`) bypasses WordPress entirely. It is often accessible server-side with no auth because it relies on CORS to block browser access. Test with curl immediately when found.

---

## Nonce Requirement Check

Try any AJAX action without a nonce first. If you get a `0` or `{"success":false}` response, a nonce is required. If you get a 403 HTML page, the WAF is blocking non-browser requests entirely.

**"test failed!" response** = plain-text WP nonce check failure. The action exists and executed, but the nonce was missing or invalid. (Confirmed on tearapart.com — all `sif_*` actions return this string with HTTP 200 when nonce is absent.)

**Extracting a nonce server-side:** A plain `requests.get(inventory_url)` is sufficient — no cookie or session needed. The nonce is in a public `wp_localize_script()` JS object embedded in the page source. Use regex: `"<plugin_nonce_key>":"([^"]+)"`. Note: custom plugins use their own nonce field names (not the WP default `_wpnonce`) — check the plugin JS to find the exact POST param name (e.g., `sif_verify_request` on tearapart.com).

WP nonces are valid for ~12 hours and must be refreshed per run.

**When nonce + WAF blocks server-side calls:** Fall back to the legacy `action=getVehicles` which returns HTML but requires no auth.

---

## Response Format Notes

- **Legacy WP AJAX actions** return raw HTML fragments, not JSON — parse with BeautifulSoup
- **Newer WP AJAX actions** return `{"success": true, "data": [...]}` JSON wrapper
- **Direct backend APIs** return bare JSON arrays

When parsing the legacy HTML table (`vehicletable1`), the date is in a `data-value` attribute on the `<td>` element, not the visible text.

---

## Record Limits / Pagination

- `getVehicles` (HTML): no observed limit — returns all matching vehicles
- `pns_get_inventory_assets` (JSON via WP): no observed limit per yard
- Direct app API (`app.pullnsaveapp.com`): **hard cap of 100 records** regardless of filters; no pagination parameters discovered

If a response always returns exactly N records, assume a cap and iterate by narrower filters (make × store).

---

## Full Inventory Without Pagination

When an endpoint caps results, iterate by:
1. **Store × Make** — fetch every store + every make combination, deduplicate by `stockId`/`StockId`
2. **Year ranges** — if make list is large, narrow by decade ranges

Get the makes list from `getMakes` (no auth). Get stores list from `getStores` (no auth).

---

## Image URL Pattern (Pull-N-Save / pullnsaveapp)

```
https://app.pullnsaveapp.com/v1/Vehicles/Images/StockId/{stockId}/OrderId/{1-4}
```
No auth. `stockId` includes the suffix (e.g., `STK130261-1`). Up to 4 images per vehicle.

---

## Deduplication Key

`stockId` / `StockId` — consistent across all endpoints (HTML table `Stock#` column, JSON `stockId` field, image URL path). Use as primary key.

---

## Anti-Bot / WAF Notes (Pull-N-Save)

- Cloudflare WAF on `pullnsave.com`
- Legacy `admin-ajax.php` actions pass through without browser fingerprinting
- Newer actions need `X-Requested-With: XMLHttpRequest` header minimum; full 403 without it
- Direct `app.pullnsaveapp.com` API has no WAF — no rate limiting observed
- No `robots.txt` restrictions on inventory pages observed

---

## WordPress Site with Direct CSV Export (iPull-uPull)

- **Site:** ipullupull.com — WP + custom `ipullupull-catalog` plugin
- **Skip the plugin API entirely.** Each yard publishes a full daily CSV at `/{yard}.csv` (e.g., `/fresno.csv`). No auth, no nonce, plain HTTP GET.
- CSV schema: `Date Added, Year, Make, Model, VIN, Stock#, Yard, Row, Fresh Set` — all columns after `Date Added` have a leading space in the header; strip on read.
- `Fresh Set = Yes` marks the newest batch of arrivals — use as incremental check.
- Location address/contact data is in JSON-LD `AutoDealer` blocks on `/locations/{city}-ca/` pages — no scraping needed, one parse per page.
