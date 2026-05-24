# Wrench A Part — Inventory Scraping Strategy

**Site:** https://wrenchapart.com/vehicle-search  
**API Base:** https://api.wrenchapart.com  
**Locations:** 7 yards across Texas (Austin area, San Antonio area, Lubbock, Belton, Holland)

---

## ✅ VIN Available

VINs are included in every vehicle record from the API. No special handling required.

---

## Platform

Custom REST API hosted on Google Cloud (Google Frontend server). No authentication required. CORS is fully open (`access-control-allow-origin: *`), so requests can be made directly from any client. Not a known third-party SaaS platform.

---

## Locations

| Yard ID | Name        | Address                          | City        | State | ZIP   | Phone          |
|---------|-------------|----------------------------------|-------------|-------|-------|----------------|
| 2       | Austin      | 5055 Hwy 71 East                 | Del Valle   | TX    | 78617 | (512) 501-6946 |
| 3       | Lubbock     | 4210 E. Slaton Highway           | Lubbock     | TX    | 79404 | (806) 745-8733 |
| 4       | Belton      | 4497 US Hwy 190 West             | Belton      | TX    | 76513 | (254) 831-4905 |
| 5       | San Antonio | 5814 Interstate 10 E.            | San Antonio | TX    | 78219 | (210) 951-5000 |
| 8       | Holland     | 24759 State Hwy 95               | Holland     | TX    | 76534 | (512) 593-4413 |
| 9       | Primo       | 5021 E. Highway 71               | Del Valle   | TX    | 78617 | (512) 247-2211 |
| 10      | Roosevelt   | 10606 Roosevelt Ave              | San Antonio | TX    | 78221 | (210) 686-0365 |

Location details are also available via the API:
```
GET https://api.wrenchapart.com/locations
```
Returns full JSON with city, street, zip, phone, social URLs, and slug per location. Use this endpoint to keep location data fresh.

---

## API Endpoints

All endpoints are unauthenticated, return JSON, and are hosted at `https://api.wrenchapart.com`.

### Reference Data

| Endpoint | Description |
|----------|-------------|
| `GET /locations` | All yard locations with address, phone, social links |
| `GET /v1/makes` | All vehicle makes with numeric IDs |
| `GET /v1/models?makeId={id}` | Models for a given make |

### Inventory

| Endpoint | Description |
|----------|-------------|
| `GET /v1/vehicles` | **All inventory across all yards** (~11,400 vehicles, single response, no pagination) |
| `GET /v1/vehicles?locationId={id}` | Inventory for a single yard |
| `GET /v1/vehicles?makeId={id}` | Inventory filtered by make |
| `GET /v1/vehicles?days={n}` | Vehicles added in the last N days (all yards) |
| `GET /v1/vehicles?locationId={id}&days={n}` | Recent arrivals for a specific yard |

**No pagination** — the full inventory is returned in a single array. The entire dataset is ~11,400 vehicles and loads in one request.

### Vehicle Record Schema

```json
{
  "yard": 2,
  "modelYear": 2008,
  "make": { "id": 18, "name": "HONDA" },
  "model": { "id": 358, "makeId": 18, "name": "ACCORD" },
  "photo": "https://storage.googleapis.com/wrench-car-photos/v1%2F2%2F1HGCP26838A061058%2F1777648958441.png",
  "vin": "1HGCP26838A061058",
  "color": "RED",
  "stockNumber": "AWAP080687",
  "dateAdded": "2026-05-04T13:32:39.547Z",
  "row": {
    "id": 119,
    "latitude": "30.18950981895418",
    "longitude": "-97.5638596758833"
  }
}
```

Fields:
- `yard` — numeric yard/location ID (maps to `id` in `/locations`)
- `modelYear` — integer year
- `make` / `model` — objects with `id` and `name`
- `photo` — Google Cloud Storage URL, or `null` if no photo
- `vin` — full 17-character VIN (always present)
- `color` — string, may be empty `""`
- `stockNumber` — yard-specific stock number (prefix varies by location, e.g. `AWAP` for Austin)
- `dateAdded` — ISO 8601 UTC timestamp
- `row.id` — physical row ID in the yard
- `row.latitude` / `row.longitude` — GPS coordinates of the row (may be `null` for some yards)

---

## Scraping Strategy

### Full Inventory Pull

Single request fetches everything:
```
GET https://api.wrenchapart.com/v1/vehicles
```

To pull per-location (better for targeted updates):
```python
LOCATION_IDS = [2, 3, 4, 5, 8, 9, 10]
for loc_id in LOCATION_IDS:
    resp = requests.get(f"https://api.wrenchapart.com/v1/vehicles?locationId={loc_id}")
    vehicles = resp.json()
```

### Incremental / Delta Updates

Use the `days` parameter to fetch only recent additions:
```
GET https://api.wrenchapart.com/v1/vehicles?days=7
```

Or per location:
```
GET https://api.wrenchapart.com/v1/vehicles?locationId=2&days=10
```

The site exposes dedicated "recent arrivals" pages (one per location) that call this endpoint:
- `https://wrenchapart.com/recent-arrivals-in-austin/?recent=true&loc=AUSTIN%20WRENCH%20A%20PART`

These pages call `/v1/vehicles?locationId={id}&days=10` under the hood.

**Recommended incremental strategy:** On each run, fetch `/v1/vehicles?days=N` where N equals the number of days since the last run. Compare VINs against previously stored records. If no new VINs appear in the recent response, the run is current. Because the `days` parameter is the only date filter available (no `after=date` support confirmed), use a rolling window approach.

### Persistence Recommendations

- **Primary key:** `vin` (always populated, 17-char, globally unique)
- **Secondary key:** `stockNumber` + `yard` (useful for re-identifying vehicles if VIN is ever blank)
- Track `dateAdded` to support time-based queries without re-fetching everything
- The `row` coordinates are useful for building a yard map but aren't needed for basic inventory tracking

---

## Recent Arrivals

The site has per-location recent arrivals pages that use `?days=10`. For incremental runs, consider using `?days=2` or `?days=3` and comparing VINs to known inventory. If all returned VINs are already known, you can skip the full pull.

---

## Notes

- No rate limiting observed during exploration
- No authentication required (no API key, session, or token)
- The API is served by Google Cloud (Google Frontend), not a standard CDN
- `yardId` and `locationId` appear to be aliases — both accept the same numeric IDs
- `page` and `limit` query params are accepted but do not affect the response (full array always returned)
- `after=date` and `dateAdded=date` filters are not supported — use `days=N` instead
- Lubbock and Holland rows may lack GPS coordinates (`latitude: null`)
- Stock number prefixes vary by location (e.g., `AWAP` for Austin/Primo, `STK` for Holland)
