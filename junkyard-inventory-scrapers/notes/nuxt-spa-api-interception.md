# Nuxt SPA Junkyard Sites — Recon Patterns

**Applies to:** u-pullandsave.com (confirmed)

---

## How to Find the API Fast

1. **Intercept network requests during UI interaction** — SPA sites make XHR/fetch calls as you use dropdowns. Attach `page.on('request')` and `page.on('response')` listeners before interacting with any form element. Filter to the site's own domain, exclude `_nuxt/`, `cdn-cgi/`, analytics noise.

2. **Cascade dropdowns reveal the URL pattern** — Year → Make → Model dropdowns each fire a GET on selection. The URL structure directly mirrors the hierarchy:
   - Select year → `GET /api/vehicles/make/{year}`
   - Select make → `GET /api/vehicles/model/{year}/{make}`
   - Select model → next call (parts list or search) revealed

3. **Selecting the final dropdown or clicking Search reveals the search endpoint** — The search fires on form submit, not on dropdown change. Capture it by attaching listeners before clicking the submit/Go button.

4. **Check `window.__NUXT__` for embedded config** — Nuxt apps sometimes serialize state into `window.__NUXT__`. On this site it was null, but worth checking. Also check inline `<script>` blocks for a `runtimeConfig` or `appConfig` object that may contain an API base URL.

5. **Check the homepage separately** — The homepage often calls different endpoints (e.g. new arrivals, hero images) that the search page doesn't. The `/api/vehicles/recent/{storeId}` endpoint was only discovered by monitoring the homepage load, not the search page.

---

## Key Findings — u-pullandsave.com

- API is fully public, no auth, no nonce, no CSRF token required
- All API calls are `GET` — no `POST` observed for data retrieval
- Search requires `year + make + model` — omitting any one param returns `[]` (no error, just empty)
- Despite the UI only showing vehicles matching the searched year, the API returns interchange-compatible years (a 2010 Honda Civic search returns 2006–2015 Civics)
- No pagination — full result set in one response
- Store ID is a numeric param (`store=105`), not a slug — inspect the location dropdown's option values to find it
- Vehicle detail (`/api/vehicles/{vehicleID}`) returns full specs decoded from VIN including trim, engine, transmission, drivetrain

## Endpoints Summary

```
GET /api/vehicles/recent/{storeId}            # new arrivals, ordered by yard entry date
GET /api/vehicles/make/{year}                 # makes available for year
GET /api/vehicles/model/{year}/{make}         # models for year+make, includes Hollander mmdCD
GET /api/vehicles/search/?store=&year=&make=&model=  # inventory search, all 3 params required
GET /api/vehicles/{vehicleID}                 # full detail: VIN, specs, images, yard row
GET /api/interchange/parts/{year}/{model}/    # part types for a vehicle
GET /api/interchange/{year}/{model}/{partType}/  # Hollander interchange numbers for a part
```

---

## Full Inventory Without a "Dump All" Endpoint

When there's no all-inventory endpoint, enumerate by building a matrix:
1. Fetch all makes for each year → `O(years)` calls
2. Fetch all models for each `(year, make)` → `O(years × makes)` calls  
3. Search every `(year, make, model)` combo → `O(combos)` calls

The make/model lists are interchange-catalog data (not just in-yard data), so most combos return `[]`. The matrix only needs refreshing weekly. Use the `/recent/` endpoint as a fast daily change-detection signal.
