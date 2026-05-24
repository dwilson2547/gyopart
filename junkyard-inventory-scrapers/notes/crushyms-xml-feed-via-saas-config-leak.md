# CrushYMS XML Feed — Discovery via SaaS Config Endpoint

**Applies to:** usautosupplymi.com (confirmed), utpap.com / Utah Pic-A-Part (confirmed — multi-location yard, both Orem and Ogden). Likely generalises to any junkyard running the **VinPlus / TexnRewards** SaaS platform.

---

## Platform Fingerprints

- Inventory page is a DataTables grid (often 100+ pages of results).
- Network traffic includes calls to `inventory-search-api-*.run.app` (Google Cloud Run), indicating a third-party SaaS backend.
- Endpoints seen: `/api/vehicle-groups`, `/api/yard-info/{yard_id}`, `/api/admin/yard-config/{yard_id}`, `/api/analytics/inventory-stats`.

---

## Key Finding: Admin Config Leaks the Raw XML Feed URL

`GET /api/admin/yard-config/{yard_id}` returns plain JSON with no auth:

```json
"inventory_file": {
  "inventory_url": "http://<ip>/<id>_inventory.xml",
  "yms_system": "crush"
}
```

This URL is a **CrushYMS** export — a single unauthenticated HTTP request that returns the complete inventory as XML, including fields the public website deliberately hides.

**Hidden fields exposed by the feed (not shown on the website):**
- `VIN` — full 17-character VIN for every vehicle
- `REFERENCE` — engine/drivetrain reference code
- `LASTUPDATE` — YMS last-modified timestamp

---

## XML Feed Structure

Root element: `<INVENTORY>` (or similar). Children: `<ASSET>`.

Key `<ASSET>` child elements:

| Tag | Content |
|-----|---------|
| `STOCKNUMBER` | Yard's canonical ID, e.g. `STK178314` — use as dedup key |
| `VIN` | 17-char VIN (occasionally absent on pre-1981 vehicles) |
| `iYEAR` | Model year (int) |
| `MAKE` | e.g. `FORD` |
| `MODEL` | e.g. `F-150` |
| `COLOR` | e.g. `WHITE` |
| `MILEAGE` | Odometer reading |
| `YARD_IN_DATE` | Arrival date (ISO-like string, strip subseconds) |
| `HOL_MODEL` | Internal HOL model code |
| `REFERENCE` | Engine reference |
| `VEHICLE_ROW` | Physical row/location in the yard |
| `LOCATION` | Human-readable location string |
| `LASTUPDATE` | Last YMS update timestamp |
| `iSTATUS` | Vehicle status (e.g. active/pulled) |

Use `STOCKNUMBER` as the dedup key — it is always present, is stable for the vehicle's lifetime in the yard, and is the same ID shown on the public website's Img column.

---

## Approach

1. Intercept browser network traffic on the inventory page.
2. Find the `/api/admin/yard-config/{yard_id}` call and read `inventory_file.inventory_url`.
3. `GET` the XML URL directly with `requests` — no auth, no browser needed.
4. Parse with `xml.etree.ElementTree`; iterate `<ASSET>` elements.
5. Mark vehicles absent from the latest feed as inactive (soft-delete pattern).

One request replaces 100+ paginated page loads and yields higher-quality data.

---

## Generalisation Notes

- The `yard_id` slug in the API path matches the value used in front-end JS (check page source or network calls for it).
- Other yards on this platform likely have the same config endpoint and the same XML feed pattern — the feed URL format is `http://<yms-server-ip>/<yard-numeric-id>_inventory.xml`.
- CrushYMS is widely used by US junkyards; the XML schema is consistent across yards.
- The SaaS config endpoint is intentionally public (consumed by client-side JS) — this is by design, not a security flaw, but it is rarely documented.
