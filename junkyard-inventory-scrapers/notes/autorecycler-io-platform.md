# autorecycler.io Platform — Recon Findings

**Applies to:** ryanspickapart.com (confirmed), likely any junkyard with an `app.autorecycler.io/inventory/{slug}` iframe

---

## Identifying the Platform

- The inventory page embeds an `<iframe>` pointing to `https://app.autorecycler.io/inventory/{slug}`
- The slug is the yard's unique ID, visible in the iframe src. Also accessible directly without the iframe.
- Navigating directly to `https://app.autorecycler.io/inventory/{slug}` works and is cleaner to scrape.
- Site title is "Inventory - {yard name}", powered by the autorecycler.io / autoscrapzen SaaS platform.

---

## API Architecture

All data comes from `https://app.autorecycler.io/elasticsearch/` endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/elasticsearch/msearch` | POST | Inventory search (paginated, infinite scroll) |
| `/elasticsearch/mget` | POST | Bulk fetch by ID (org config, makes, models) |
| `/elasticsearch/maggregate` | POST | Aggregations (counts per make/model) |
| `/elasticsearch/search` | POST | Generic search |
| `/api/1.1/init/data` | GET | App bootstrap — loads website config JSON (yard name, address, total count) |

**Critical:** All POST request bodies are AES-encrypted (fields `z`, `y`, `x` in JSON). Responses are plain JSON. Direct `requests` replay is not possible.

---

## Getting the Total Vehicle Count

The `GET /api/1.1/init/data?location=https://app.autorecycler.io/inventory/{slug}` response is clear JSON. The `mget` response for the org record contains `crush_total_count_number` — the current total yard inventory count. Useful for knowing when a scroll loop has collected everything.

---

## Inventory Response Shape

Each `msearch` response has `responses[].hits.hits[]`. Filter by `_type == "custom.inventorysearch"`.

Key fields in `_source`:

| Field | Content |
|-------|---------|
| `_id` | Stable unique ID — use as dedup key |
| `stock_number_text` | e.g. `STK218958` |
| `name_text` | `"YEAR MAKE MODEL"` — e.g. `"2015 Chevrolet Equinox"` |
| `vehicle_year_number` | int |
| `exterior_color_text` | e.g. `"BLACK"` |
| `vin_text` | 17-char VIN |
| `row_text` | yard row number (string) |
| `added_date_date` | epoch milliseconds |
| `preview_image_image` | `//cdn.bubble.io/...jpeg` — prepend `https:` |
| `vehicle_make_custom_vehicle_make` | opaque reference ID — make name is in `name_text` |
| `vehicle_model_custom_vehicle_model` | opaque reference ID — model name is in `name_text` |
| `inventory_id_text` | inventory record ID |

`name_text` is the most reliable source for year/make/model — the separate make/model fields are only opaque reference IDs.

---

## Pagination / Infinite Scroll

- The page uses infinite scroll — no URL changes, no "next page" button.
- Each downward scroll triggers a new `msearch` POST.
- Each response includes `"at_end": true/false` at the top level of each response object.
- Scroll loop strategy: scroll to `document.body.scrollHeight`, wait ~2.5s for network idle, repeat until no new vehicles for N consecutive scrolls (6 works well).
- ~1422 vehicles at Ryan's Pick-a-Part loads fully in ~30-60 scrolls.

---

## How to Scrape It

Use Playwright with a response listener — do not attempt `requests`.

```python
async def handle_response(response):
    if "elasticsearch/msearch" not in response.url:
        return
    data = json.loads(await response.body())
    for resp in data.get("responses", []):
        for hit in resp.get("hits", {}).get("hits", []):
            if hit.get("_type") == "custom.inventorysearch":
                # process hit["_source"]
```

Attach before `page.goto()`. No auth, no cookies, no special headers required — the iframe loads without any session.

---

## robots.txt

`ryanspickapart.com/robots.txt` — returned a blank/default response (no Disallow rules observed for inventory paths).
`app.autorecycler.io` is the actual data host — no robots.txt restrictions observed.
