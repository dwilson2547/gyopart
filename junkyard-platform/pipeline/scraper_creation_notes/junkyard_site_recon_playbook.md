# Junkyard Site Recon Playbook

**Author:** Scraper recon agent  
**Created:** 2026-05-18  
**Context:** Derived from hands-on recon of pullnsave.com. Intended as a repeatable methodology for agents tasked with building new junkyard inventory scrapers.

---

## Overview

Junkyard inventory sites tend to fall into a small number of architectural patterns. Identifying which pattern a site uses early — before writing any scraper code — determines the entire approach. This document records the indicators to look for and the investigation steps that work reliably.

---

## Step 1 — Baseline Page Recon

Before touching network traffic, load the inventory search page and read its static HTML source.

### What to look for

**1. Inline JavaScript variable blocks**

Sites that use WordPress or custom CMS plugins almost always inline configuration variables into the page in a `<script>` block:

```js
var some_ajax = {
  "url": "https://example.com/wp-admin/admin-ajax.php",
  "nonce": "abc123def",
  "apiurl": "https://app.example.com/v1/Vehicles/Search"
};
```

These blocks reveal:
- The AJAX dispatcher URL
- Any nonce/token needed for newer endpoints
- Sometimes a **separate backend API hostname** (high value — see Step 4)

**Regex to extract:** `"apiurl"\s*:\s*"([^"]+)"` and `"nonce"\s*:\s*"([^"]+)"`

**2. External script tags**

Collect all `<script src="...">` tags that are not Google/Facebook/GTM. Plugin-specific JS files often have names like:
- `vehicle-search.js`
- `pns-inventory-functions.js`
- `custom.js`

Fetch and read these — they contain the complete client-side API interaction logic. This is faster than live network interception for understanding all available endpoints.

**3. Form field IDs and names**

Read the search form HTML directly. It tells you:
- Exact POST field names (`name="pns_make"`, `name="search_type"`)
- Whether the site uses numeric IDs or text values for makes/models
- Whether yard selection is single or multi-select
- What the "All" sentinel values are (e.g., `value="0"` = any model)

---

## Step 2 — Read the Plugin JS Files

Fetching the custom JS files is often the single highest-return action in a recon. You can read them via `fetch_webpage` or `curl`.

### What to extract

- **All `$.post(url, {...})` and `$.ajax({url:..., data:...})` calls** → these are every available backend action
- **The `action:` values** passed in the POST body → these are the AJAX handler names (e.g., `getVehicles`, `getMakes`, `getStores`)
- **The data field names** for each action → these become your POST body parameters
- **Response handling code** (`function(data){...}`) → reveals response format (HTML vs JSON) and the fields to expect
- **Any secondary API URLs** embedded as strings (e.g., `https://app.example.com/v1/...`)

### Indicator: WordPress Admin AJAX pattern

If you see `wp-admin/admin-ajax.php` as the POST URL, the site is using WordPress's standard AJAX dispatcher. All actions are registered server-side as `wp_ajax_nopriv_{action}` (no login required) or `wp_ajax_{action}` (login required). The `action` field in the POST body routes the request.

**Key insight:** `wp_ajax_nopriv_*` actions work from server-side `curl`/`requests` without any cookies. `wp_ajax_*` (auth-gated) and newer nonce-protected handlers may require a browser session or valid nonce.

---

## Step 3 — Identify the Authentication Model

Test each discovered action from server-side (no cookies, no browser) immediately. This tells you which endpoints are "free" vs. which need auth.

### Test pattern (curl)

```bash
curl -s -X POST 'https://example.com/wp-admin/admin-ajax.php' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'action=getStores'
```

### Possible outcomes and what they mean

| Response                        | Meaning                                                      |
|---------------------------------|--------------------------------------------------------------|
| Valid JSON/HTML data            | Endpoint is fully open — scrape directly                     |
| `{"success":false,"data":-1}`   | WP nonce required — extract from page HTML and include as `security=<nonce>` |
| `{"success":false,"data":-2}`   | Nonce expired — must re-fetch from a fresh page load         |
| `403` or Cloudflare challenge   | WAF blocking non-browser requests — fall back to a different endpoint or use Playwright |
| `{"success":true,"data":[null]}`| Endpoint reached but returned no data — check required params (e.g., make filter may be mandatory) |

### Nonce handling

WordPress nonces are **10-character hex tokens** embedded in the page HTML. They are typically valid for 12–24 hours. For a scraper:

1. Fetch the inventory page HTML
2. Extract with regex: `"nonce":"([a-f0-9]{10})"`
3. Include as `security=<nonce>` in POST body
4. If the endpoint starts returning `-2`, re-fetch the page and get a fresh nonce

---

## Step 4 — Look for a Separate Backend API

Many junkyard sites are built as WordPress frontends that proxy to a **separate mobile-app-grade REST API**. This is the highest-value discovery in recon because:

- The API often has no CORS restrictions from server-side
- It returns structured JSON vs HTML tables
- It may expose more fields than the WordPress layer shows (e.g., VIN, transmission, engine)
- It is often the same API used by the site's iOS/Android app

### Indicators to look for

- An `apiurl` field in the inline config variable (see Step 1)
- References to a subdomain like `app.`, `api.`, `mobile.`, `enterpriseservice.`, `inventoryservice.`
- Image URLs pointing to a different domain than the main site (e.g., `https://app.pullnsaveapp.com/v1/Vehicles/Images/...`)

### Testing the backend API

Once a backend API URL is known, try:

```bash
# Try a broad search with minimal params
curl -s -X POST 'https://app.example.com/v1/Vehicles/Search' \
  -H 'Content-Type: application/json' \
  -d '{"make":"","model":"","yard":[]}'
```

If it returns data, check:
- **Record count** — is it capped? Common caps are 100, 250, 500
- **Pagination** — try adding `"page":2` or `"offset":100` to see if it's supported
- **Yard/store filtering** — pass each known store ID individually and compare `storeRno` in the response to confirm the filter actually works
- **Auth requirements** — try without any headers first; add `Origin: https://www.maindomain.com` if needed

### Warning: Capped backend APIs

If every combination of params returns exactly the same count (e.g., always 100), the API has a hard cap. Options:
- Filter by make to get < 100 results per request, then iterate over all makes
- Fall back to the WordPress AJAX HTML endpoints which may not have this cap
- Filter by date ranges if supported

---

## Step 5 — Map the Data Model

Once you have at least one working endpoint returning data, catalog the full field set. Cross-reference across both endpoints if there are two (WordPress AJAX and backend API), as they sometimes return different fields.

### Junkyard inventory universal fields

Every junkyard site exposes some version of these. Note the exact field names per site:

| Concept         | Common names                              |
|-----------------|-------------------------------------------|
| Unique vehicle key | `stockId`, `ticketID`, `vehicleRno`, `stockNumber` |
| Store/yard       | `storeRno`, `locID`, `StoreNumber`, `yardId` |
| Year             | `year`, `modelYear`                       |
| Make             | `make`, `makeName`                        |
| Model            | `model`, `modelName`                      |
| VIN              | `vin`                                     |
| Color            | `color`                                   |
| Yard row         | `yardRow`, `row`                          |
| Date arrived     | `rcvdDtTm`, `dateYardOn`, `dateReceived`  |

### Checking for nulls

Run a sample of ~50 records and note which fields are consistently `null`. For Pull-N-Save, `transmissionDesc` and `engineDesc` were always null in the backend API — suggesting these fields exist in the schema but are not populated. Don't build scraper logic around consistently-null fields.

---

## Step 6 — Discover the Stores/Locations Endpoint

Almost every junkyard chain exposes a locations endpoint before the inventory endpoint. Always find and call it first — the IDs it returns are required for inventory queries.

### Common patterns

- WordPress AJAX: `action=getStores` → JSON array of `{StoreNumber, StoreName, State}`
- REST API: `GET /v1/Locations` or `GET /v1/Stores` or `GET /Location?siteTypeID=-1`

If a dedicated endpoint isn't found, the store IDs can usually be extracted from the HTML `<select>` in the search form (the `<option value="N">` values).

---

## Step 7 — Validate Response Completeness

Before finalizing the scraping strategy, validate that your approach captures the full inventory and not just a subset.

### Completeness checks

1. **Store-by-store count comparison:** Query the same make across multiple stores. Do counts vary by store? If every store returns the same count (especially a round number like 100), you have a cap problem.

2. **Cross-check with the site's UI:** Load a specific yard in the browser, submit the search, note the result count shown. Compare to what your API calls return for the same params.

3. **Deduplication test:** Collect results for the same yard via two different endpoints (e.g., `getVehicles` HTML and the backend JSON API). Normalize `stockId` and check for overlap — this reveals which source has the fuller dataset.

4. **Date range probe:** Retrieve results for a very specific date (e.g., `beginDate=2026-05-15&endDate=2026-05-15`). If the endpoint supports it, use date-windowed queries to manage large inventories.

---

## Step 8 — Image URL Pattern

Junkyard scrapers often need vehicle photos for downstream use (visual duplicate detection, condition assessment, etc.). The image URL is almost always a predictable pattern based on stock ID.

### Common patterns

```
# Pattern 1: StockId + OrderId
https://api.example.com/v1/Vehicles/Images/StockId/{stockId}/OrderId/{1..4}

# Pattern 2: Ticket/Line
https://api.example.com/images/{ticketId}/{lineId}/{imageIndex}.jpg

# Pattern 3: CDN with hash
https://cdn.example.com/vehicles/{hash}.jpg
```

To discover the pattern:
1. Find an `<img>` tag in the HTML response from `getVehicles` or similar
2. Extract the URL structure
3. Test substituting a different StockId from the same response to confirm predictability
4. Test OrderId/index values 1–4 (most sites store up to 4 images per vehicle)

---

## Anti-Scraping / WAF Considerations

### Cloudflare (common on WordPress sites)

- The `wp-admin/admin-ajax.php` endpoint is commonly behind Cloudflare
- Legacy `nopriv` AJAX actions usually pass through because they have legitimate use (public inventory lookups)
- Newer nonce-protected actions may trigger challenges without browser-like headers
- A 403 response that is ~75KB is typically a Cloudflare block page (actual data responses are much smaller)

### Mitigation strategies (in order of preference)

1. **Use open endpoints** — legacy AJAX actions that work without nonce/cookies are the first choice
2. **Use the backend API directly** — if a separate API hostname exists and returns data without auth, it bypasses the WP/Cloudflare layer entirely
3. **Nonce extraction** — for nonce-protected endpoints, fetch the page to get a fresh nonce before each batch of requests
4. **Playwright fallback** — for fully browser-gated endpoints, drive a headless browser, intercept the XHR responses, and extract the JSON payload directly

### Rate limiting

- Start with 1–2 second delays between requests
- Junkyard sites are low-traffic and rarely have aggressive rate limiting
- If you receive 429s, back off exponentially

---

## Decision Tree: Choosing the Scraping Approach

```
Is there a separate backend API hostname? (app.*, api.*, mobile.*, enterpriseservice.*)
├── YES → Test it directly with curl (no auth). Does it return data?
│         ├── YES → Use backend API. Check for caps. Iterate by make/store if needed.
│         └── NO (403/CORS from server) → Backend is blocked; use WP AJAX instead.
│
└── NO → Is there a WordPress admin-ajax.php URL?
          ├── YES → Read plugin JS. List all action= values. Test each without auth.
          │         ├── Some work → Use open actions (getVehicles, etc.) as primary.
          │         └── All need nonce → Extract nonce from page HTML, include as security=.
          └── NO → Site is fully server-rendered or uses a custom framework.
                    → Use Playwright to intercept XHR, or parse full HTML pages.
```

---

## Site-Specific Notes Index

This folder is intended to accumulate per-site findings. Each file should document:
- Which pattern the site matched
- What worked and what didn't
- Any quirks or undocumented behavior
- Confirmed field names and their meanings

| File                              | Site             | Date        |
|-----------------------------------|------------------|-------------|
| *(this file)*                     | General playbook | 2026-05-18  |
| *(add per-site notes files here)* |                  |             |
