# U-Pull and Save — Inventory Scraper

**Site:** https://www.u-pullandsave.com/  
**Location:** Pontiac, MI (store ID `105`) — Mason, MI yard is closed  
**Stack:** Nuxt.js SPA with an unauthenticated public REST API  
**~Inventory size:** ~1,300 vehicles in yard, up to 150 added per week

---

## API Reference

All endpoints are unauthenticated. Base URL: `https://www.u-pullandsave.com`

### New Arrivals

```
GET /api/vehicles/recent/{storeId}
```

Returns the most recently added vehicles (ordered by yard entry date). Fast change-detection signal.

**Example:** `GET /api/vehicles/recent/105`

**Response:**
```json
[
  {
    "vehicleMake": "ACURA",
    "modelYear": 2004,
    "modelName": "RSX",
    "storeNumber": 105,
    "yardLocationDT": "2026-05-15T09:28:17.090Z",
    "vehicleID": 15918486
  }
]
```

---

### Makes for a Year

```
GET /api/vehicles/make/{year}
```

Returns all makes available in the interchange database for a given model year. Used to build the year/make/model matrix.

**Example:** `GET /api/vehicles/make/2010`

**Response:**
```json
[
  { "vehicleMake": "Acura" },
  { "vehicleMake": "Honda" },
  ...
]
```

---

### Models for a Year + Make

```
GET /api/vehicles/model/{year}/{make}
```

Returns all models for a given year and make. Also returns Hollander interchange metadata.

**Example:** `GET /api/vehicles/model/2010/Honda`

**Response:**
```json
[
  {
    "trueModel": "Civic",
    "hollanderModel": "Civic",
    "mmdCD": "HO1",
    "mmdCategory": "C"
  }
]
```

---

### Vehicle Search (Inventory)

```
GET /api/vehicles/search/?store={storeId}&year={year}&make={make}&model={model}
```

Returns vehicles currently in the yard matching the given criteria. **All three of `year`, `make`, and `model` are required** — omitting any returns `[]`.

The `year` parameter acts as an interchange year, so a search for `2010/Honda/Civic` may return Civics from adjacent model years with compatible parts.

**Example:** `GET /api/vehicles/search/?store=105&year=2010&make=Honda&model=Civic`

**Response:**
```json
[
  {
    "vehicleID": 15918288,
    "stockID": "P52173",
    "modelYear": 2011,
    "modelMake": "HONDA",
    "modelName": "Civic",
    "colorOfVehicle": "SILVER",
    "yardRow": 37
  }
]
```

No pagination observed — all matching results are returned in a single response.

---

### Vehicle Detail

```
GET /api/vehicles/{vehicleID}
```

Returns full detail for a single vehicle including VIN, specs, yard location, and images.

**Example:** `GET /api/vehicles/15918288`

**Response:**
```json
{
  "vehicleID": 15918288,
  "storeNumber": 105,
  "vehicleRno": 52525,
  "stockID": "P52173",
  "VIN": "2HGFA1F93BH522866",
  "modelYear": 2011,
  "vehicleMake": "HONDA",
  "modelName": "CIVIC",
  "colorOfVehicle": "SILVER",
  "odometerReading": 0,
  "odometerSts": null,
  "YardLocation": "YARD",
  "YardLocationDT": "2026-05-15T09:04:35.143Z",
  "YardRow": 37,
  "ProofDocs": "CLEAR/CLEAN",
  "ForSalePrice": null,
  "forSaleDate": null,
  "websiteDescription": null,
  "images": [
    {
      "imageID": 290664,
      "referenceID": 15918288,
      "displayOrder": 0,
      "image": "https://static.u-pullandsave.com/68fcc72f-06c9-47ee-950c-ce31a8082684.jpg",
      "imageSmall": "https://static.u-pullandsave.com/small/68fcc72f-...",
      "imageMedium": "https://static.u-pullandsave.com/medium/68fcc72f-...",
      "imageLarge": "https://static.u-pullandsave.com/large/68fcc72f-..."
    }
  ],
  "vehicleSpecifications": {
    "vehicleSpecID": 84496,
    "modelYear": 2011,
    "vehicleMake": "Honda",
    "vehicleModel": "Civic",
    "trim": "EX-L",
    "shortTrim": "EX-L",
    "trimVariations": "EX L",
    "madeIn": "Canada",
    "vehicleStyle": "5-Speed",
    "vehicleType": "Sedan",
    "vehicleSize": "Compact",
    "vehicleCategory": "Subcompact Car",
    "doors": "4",
    "fuelType": "Gasoline",
    "fuelCapacity": "13.20 gallons",
    "cityMileage": "25 miles/gallon",
    "highwayMileage": "36 miles/gallon",
    "engine": "1.8L I4",
    "engineCylinders": "4",
    "transmissionType": "Automatic",
    "transmissionGears": "5",
    "drivenWheels": "Front-Wheel Drive",
    "antiBrakeSystem": "4-Wheel ABS",
    "steeringType": "Rack & Pinion",
    "curbWeight": 2831,
    "overallHeight": "56.50 inches",
    "overallWidth": "69.00 inches"
  },
  "compNine": null
}
```

---

### Parts List (Interchange)

```
GET /api/interchange/parts/{year}/{model}/
```

Returns all part types available for a given year and model (used to populate the part dropdown in the Interchange Search UI).

**Example:** `GET /api/interchange/parts/2010/Civic/`

**Response:**
```json
[
  { "partType": "300", "description": "Engine Assembly" },
  { "partType": "601", "description": "Alternator" },
  ...
]
```

---

### Interchange Numbers for a Part

```
GET /api/interchange/{year}/{model}/{partType}/
```

Returns Hollander interchange numbers for a specific part across engine/trim variations.

**Example:** `GET /api/interchange/2010/Civic/300/`

**Response:**
```json
[
  {
    "application": "1.8L",
    "IDXID": 86801,
    "inventoryNbr": "300-80918 ",
    "seqNbr": 386,
    "treeLevel": 1
  }
]
```

---

## Scraping Strategy

The search endpoint requires all three of `year`, `make`, and `model`. There is no "dump all inventory" endpoint. The recommended approach is a two-pass strategy:

### Pass 1 — Build the Year/Make/Model Matrix (cache, refresh weekly)

1. For each year in the range (e.g. 1985–2027):
   - `GET /api/vehicles/make/{year}` → collect all makes
2. For each `(year, make)` pair:
   - `GET /api/vehicles/model/{year}/{make}` → collect all models
3. Store the full `(year, make, model)` combination table locally

Estimated API calls: ~2,000–4,000 total. Rarely changes.

### Pass 2 — Poll for Inventory (daily/nightly sweep)

For every `(year, make, model)` combo in the matrix:
```
GET /api/vehicles/search/?store=105&year={year}&make={make}&model={model}
```

Diff the returned `vehicleID` list against the previous run to detect:
- **New vehicles** (present now, not before) → fetch full detail via `GET /api/vehicles/{vehicleID}`
- **Removed vehicles** (were present, now gone) → mark as pulled/sold

### Pass 2b — Fast Change Detection (every few hours)

Poll `/api/vehicles/recent/105` as a lightweight signal. If new `vehicleID`s appear that aren't in the local DB, fetch their detail immediately without waiting for the full nightly sweep.

### Suggested Polling Schedule

| Job | Endpoint | Frequency |
|---|---|---|
| Change detection | `/api/vehicles/recent/105` | Every 2–4 hours |
| Full inventory sweep | `/api/vehicles/search/` (all combos) | Nightly |
| Matrix refresh | `/api/vehicles/make/{year}` + `/model/` | Weekly |

---

## Notes

- No authentication required on any endpoint
- No rate limiting observed during exploration
- No pagination — search results return all matches in one response
- `vehicleID` appears to be a global sequential integer (e.g. `15918486`)
- `stockID` is a yard-local stock number (e.g. `P52173`)
- Images are hosted at `https://static.u-pullandsave.com/` in four sizes: original, `small/`, `medium/`, `large/`
- The site uses [Hollander interchange](https://www.hollanderparts.com/) part numbering — the `mmdCD` field in the model response is the Hollander manufacturer code
