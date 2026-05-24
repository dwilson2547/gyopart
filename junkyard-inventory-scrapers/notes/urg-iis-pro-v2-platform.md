# URG / Inventory Insite Software (iis-pro-v2)

Platform used by auto recyclers that subscribe to URG (Used Recycled & Graded).

## Identification

- WordPress plugin: `iis-pro-v2` (path: `/wp-content/plugins/iis-pro-v2/`)
- Footer text: `Powered by URG`
- JS file: `/wp-content/plugins/iis-pro-v2/js/iisincludespro3.js` (contains all AJAX action names)
- Site-specific yard ID embedded inline: `var urgid = 'IL22';` (example)

## URL Structure (Server-Side Rendered)

All inventory pages are SSR – no AJAX needed to scrape vehicles or parts.

```
/parts/makes/                            → all makes + part counts
/parts/{MAKE}/                           → models for a make + part counts
/parts/{MAKE}/{MODEL}/                   → vehicle cards (stock, year, VIN, miles)
/parts/{MAKE}/{MODEL}/{STOCK}/{YEAR}     → individual parts for a vehicle
/latest-arrivals/                        → last 60 acquired vehicles, sorted by Purchase Date
```

## Key Data Fields

**Vehicle card** (`.iis-col-sm-4 > .card-price`, card `id` = stock number):
- Stock, Year, Make/Model, VIN, Miles
- On `/latest-arrivals/`: also includes `Purchase Date`

**Part row** (`<table id="large">`):
- Part Type, OEM Part Numbers, Details, Stock, Tag, VIN, SKU, Part Grade, Price

## Images

```
Vehicle thumbnail:  https://da8h1v3w8q6n5.cloudfront.net/{yardpath}/images/{STOCK}/{STOCK}_1.jpg
Part photo:         https://da8h1v3w8q6n5.cloudfront.net/{yardpath}/inventory/{STOCK}/{TAG}_{N}.jpg
```

> **Note:** `{yardpath}` is yard-specific, e.g. `mi34` (sturtevantauto) or `az03` (arizonaautoparts). It is the lowercase yard ID found in the image URLs, not necessarily the same as `urgid`.

## Stock Number Format

Stock numbers are **not always numeric**. Some yards use alphanumeric stock IDs with a trailing letter suffix that encodes the location (e.g. `230358A`, `260844B`). Confirmed on arizonaautoparts.com:

| Suffix | Suspected Yard (AZ03) |
|--------|----------------------|
| `A` | Phoenix |
| `B` | Tucson |
| `U` | Unknown / unclassified |

Always parse the card `id` attribute (or `<b>Stock:</b>` text) as a string, not an integer.

Images lazy-loaded; actual URL in `data-src` attribute, `src` holds placeholder.

Alternative stock photo pattern (URG CDN, requires yard ID):
```
https://images.u-r-g.com/images/yard/{YARDID}/stock/{stockno}
```

## AJAX Actions (admin-ajax.php)

Nonce: `iisNonce` variable injected inline on any page loading the plugin.  
Extraction: `/iisNonce\s*=\s*'([^']+)'/`

| Action                 | Key Params           | Use                            |
|------------------------|----------------------|--------------------------------|
| `getMakesIIS`          | `year`               | Year-filtered makes list       |
| `getModelsIIS`         | `year`, `make`       | Year-filtered models list      |
| `getpartCategoriesIIS` | –                    | All part categories            |
| `getpartTypesIISModal` | `category`           | Part types within category     |
| `getVerticalIIS`       | –                    | Year range dropdown HTML       |
| `getprefilldataIIS`    | `iisYear`, `iisMake` | Prefill search form            |

All tested without authentication on speedwayap.com. AJAX is only needed for the search widget – full crawl uses SSR pages only.

## Incremental Monitoring

`/latest-arrivals/` shows the 60 most recently acquired vehicles with `Purchase Date`. Use as an incremental starting point: stop processing when a seen stock# or VIN is encountered. Fall back to full crawl otherwise.

## URG U-Pull Variant (`iis-pro-upull`)

A distinct but closely related URG plugin for self-serve U-Pull yards. Key differences from `iis-pro-v2`:

- Plugin path: `/wp-content/plugins/iis-pro-upull/`
- Inline config uses `iisupull` prefix: `var iisupullurgid = 'MO09,MO38';` (can be comma-separated multi-yard)
- Inventory URL uses `/inventory/` dir (not `/parts/`): `/inventory/{MAKE}/{MODEL}/`
- Make list is in the page HTML `<select>` (not AJAX); models via `getAllModelsIISupull` (no year filter)
- AJAX action names end in `IISupull` (not `IIS`): `getMakesIISupull`, `getAllModelsIISupull`, `getModelsIISupull`, `getYearsIISupull`, `getprefilldataIISupull`
- **No nonce required** — all AJAX actions work auth-free
- Location filter URL param: `?id={URGID}` appended to inventory URL
- Vehicle cards use `.car-details-uPull` selector with labeled text fields (Stock, Year, Make/Model, Vin, Location, Row, Set Date)
- **No `/latest-arrivals/` with inventory** — that page is static marketing content; sort by Set Date for incremental runs

## Observed Sites

- https://speedwayap.com/ – Yard IL22, Joliet IL, single location
- https://www.las-parts.com/ – Yards NJ29, II08, NJ12, Ringoes NJ + Port Murray NJ (2 known locations), multi-yard site; location per vehicle extractable from CDN image URL prefix (`nj12`, `nj29`, `ii08`); AJAX location actions return 400
- https://midwayupull.com/ – Yards MO09 (Liberty, MO) + MO38 (Kansas City, KS "Muncie"); `iis-pro-upull` variant; 3 physical locations but only 2 in inventory system
