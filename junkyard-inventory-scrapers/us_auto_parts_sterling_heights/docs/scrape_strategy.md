# Scrape Strategy — How the XML Feed Was Discovered

## Starting point

The target URL was the public inventory page:

```
https://usautosupplymi.com/upull/sterling-heights/sterling-heights-inventory/
```

A quick `fetch` of the page returned a DataTables-powered grid showing
1,087 entries across 109 pages.  The naive approach would have been to
drive pagination through the browser, clicking "Next" 108 times.  The
investigation phase was specifically aimed at avoiding that.

---

## Phase 1 — robots.txt check

```
User-agent: *
Disallow: /wp-admin/
Allow:    /wp-admin/admin-ajax.php
Crawl-delay: 10
```

No restrictions on the inventory path.  Crawl-delay of 10 s noted.

---

## Phase 2 — Network interception on the inventory page

Instead of reading the HTML, the browser's network traffic was captured
immediately after navigation.  Filtering out static resources (images,
fonts, scripts) left a short list of dynamic requests.  Four calls to
an external Google Cloud Run service stood out:

```
GET  https://inventory-search-api-581547763015.us-central1.run.app/api/vehicle-groups          → 200
GET  https://inventory-search-api-581547763015.us-central1.run.app/api/admin/yard-config/us_auto_supply → 200
GET  https://inventory-search-api-581547763015.us-central1.run.app/api/yard-info/us_auto_supply → 200
GET  https://inventory-search-api-581547763015.us-central1.run.app/api/analytics/inventory-stats?yard_id=us_auto_supply&days=365 → 200
```

This confirmed the site uses a third-party SaaS platform
(**TexnRewards / VinPlus**) for inventory management, not a custom
backend.  The `vehicle-groups` endpoint returned a large catalogue of
makes/models — useful for the front-end search filters but not the
inventory itself.

---

## Phase 3 — Reading the admin yard config

The `/api/admin/yard-config/us_auto_supply` response was the most
revealing.  Among other settings it contained:

```json
"inventory_file": {
  "inventory_url": "http://45.79.157.162/1066_inventory.xml",
  "yms_system": "crush"
}
```

This exposed the raw CrushYMS XML feed URL directly.  CrushYMS is a
popular Yard Management System used by many US junkyards; the feed is a
standard export format.  The IP address (`45.79.157.162`) is a
Linode/Akamai host separate from the main website, suggesting it is the
junkyard's own YMS server.

> **Key insight:** Admin/config endpoints in SaaS-backed sites often
> leak internal data source URLs because they are designed to be read
> by client-side JavaScript, not hidden from the browser.  Inspecting
> all non-analytics, non-tracking network calls is almost always worth
> doing before attempting HTML scraping.

---

## Phase 4 — Validating the XML feed

A direct `GET http://45.79.157.162/1066_inventory.xml` confirmed:

- No authentication required (public HTTP)
- Single request returns the **complete** inventory (~1 MB XML)
- 1,086 `<ASSET>` records, each with `STOCKNUMBER`, `VIN`, year, make,
  model, colour, engine reference, yard row, timestamps, etc.
- **VINs are present** — the public website intentionally omits them,
  but the underlying YMS data includes full 17-character VINs for every
  vehicle

This made the entire DataTables pagination problem irrelevant: one HTTP
request replaces 109 browser-driven page loads.

---

## Strategy decision

| Option | Requests | Complexity | Data quality |
|--------|----------|------------|--------------|
| Playwright + DataTables pagination | 109+ | High | No VIN, display text only |
| `requests` + HTML scraping | 109+ | Medium | No VIN |
| **`requests` + XML feed** | **1** | **Low** | **Full, including VIN** |

The XML feed was chosen.  No browser automation is needed at runtime.

---

## Deduplication

The site does not expose VINs on the public-facing page (the readme
noted this concern).  However the XML feed contains both:

- **`STOCKNUMBER`** — the YMS stock number (e.g. `STK178314`), unique
  per vehicle intake event and stable for the vehicle's lifetime in the
  yard
- **`VIN`** — the 17-character vehicle identification number

`STOCKNUMBER` was chosen as the primary dedup key because:

1. It is always present (VINs are occasionally absent for pre-1980 or
   non-standard vehicles)
2. It is the yard's own canonical identifier — if the yard
   re-enters a vehicle it will get a new stock number, which is the
   correct behaviour (a new intake event)
3. It matches what the public website displays in the "Img" column,
   making manual cross-referencing straightforward

VINs are stored as a secondary field for enrichment purposes and can be
used for cross-yard deduplication if needed in future.

---

## Scheduling considerations

Because the feed is a single request and the XML is ~1 MB, a daily
cron job is appropriate and inexpensive.  The webcache means re-runs
within the same cache TTL window cost zero network requests.  The
`scrape_runs` table provides a full audit trail across runs, and
`is_active` tracking makes it easy to detect when vehicles leave the
yard.
