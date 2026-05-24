# inventory-7lt WordPress Plugin — SSR Paginated Inventory

**Applies to:** wegotused.com (confirmed)

---

## Identification

- WordPress plugin: `/wp-content/plugins/inventory-7lt/`
- Loads `angularjs-1.7.8.min.js` from the plugin assets directory
- AngularJS module: `angular.module("upullit", [])` with `SearchController`
- No admin-ajax — uses custom URL params directly on the inventory permalink
- Inventory HTML is **server-side rendered on page load** — no JS execution needed

## Key Findings

- **No auth, no nonce, no CSRF token** required for any request
- `inv[page]` is **0-indexed** — page=0 = records 1–15
- Page size is **15 records per page** (hardcoded)
- Total count in rendered HTML: `"Showing 1 to 15 of N records"` — parse `N` to calculate total pages
- Sorting: `inv[sort][yard_date]=0` = newest first; `inv[sort][yard_city]=0` = sort by city
- JSON sub-endpoints for dropdown population: `/our-inventory/?inv_action=get_makes`, `get_models`, `get_years`, `get_parts` — none are needed for full crawl
- AngularJS uses `jQuery("#_results").load(url + " #_results")` for filtered reloads — target `#_results` selector to avoid reparsing the full page

## API Pattern

```
GET /our-inventory/?inv[yard]=all&inv[make]=&inv[model]=&inv[manufacturer]=&inv[year]=&inv[part]=&inv[page]={N}&inv[sort][yard_date]=0
```

Returns full HTML. Extract `#_results` div. Table `tbody tr` → cells[0..8] = Yard City, Year, Make, Model, Manufacturer, Color, Yard Date, Row, VIN.

## No Recent Arrivals Page

No dedicated recent arrivals page exists. Use `inv[sort][yard_date]=0` (newest first) and stop when a known VIN is encountered.
