# Pull-A-Part API Endpoints

These endpoints were discovered via prior recon on the Pull-A-Part web app.
All are unauthenticated JSON REST endpoints — no cookies or tokens required.

---

## 1. Locations

**URL:** `GET https://enterpriseservice.pullapart.com/Location`

**Query params:**

| Param      | Value | Notes                          |
|------------|-------|--------------------------------|
| siteTypeID | `-1`  | Returns all site types         |

**Sample response (single item):**

```json
{
  "locationID": 18,
  "name": "Indianapolis",
  "address": "123 Junkyard Rd",
  "city": "Indianapolis",
  "state": "IN",
  "zip": "46201",
  "phone": "317-555-0100",
  "lat": 39.7684,
  "lng": -86.1581,
  "siteTypeID": 1
}
```

**DB table:** `locations`

---

## 2. Makes

**URL:** `GET https://inventoryservice.pullapart.com/Make/`

No parameters required.

**Sample response (single item):**

```json
{
  "makeID": 6,
  "makeName": "ACURA"
}
```

**DB table:** `makes`

---

## 3. Vehicle Inventory Search

**URL:** `POST https://inventoryservice.pullapart.com/Vehicle/Search`

**Content-Type:** `application/json`

**Request body:**

```json
{
  "Locations": [18, 22, 31],
  "MakeID": 6,
  "Models": [],
  "Years": []
}
```

> **Note:** `Locations` accepts a list of IDs. The scraper sends **all** location IDs in a
> single request per make, reducing the total request count from `N_locations × N_makes`
> down to just `N_makes` (~70 requests vs ~3,500).

**Sample response (single location block):**

```json
[
  {
    "locationID": 18,
    "exact": [
      {
        "vinID": 95697,
        "ticketID": 1081209,
        "lineID": 1,
        "locID": 18,
        "locName": "Indianapolis",
        "makeID": 6,
        "makeName": "ACURA",
        "modelID": 1098,
        "modelName": "TSX",
        "modelYear": 2004,
        "row": 303,
        "vin": "JH4CL95874C031434",
        "dateYardOn": "2024-04-29T16:37:15.673",
        "vinDecodedId": 23235,
        "extendedInfo": null
      }
    ],
    "other": [],
    "inventory": null
  }
]
```

Both `exact` and `other` arrays contain vehicle objects in the same schema.

**DB table:** `vehicles`

---

## 4. Vehicle Extended Info

**URL:** `GET https://inventoryservice.pullapart.com/VehicleExtendedInfo/{loc_id}/{ticket_id}/{line_id}`

| Path segment | Source field in vehicle object |
|--------------|-------------------------------|
| `loc_id`     | `locID`                       |
| `ticket_id`  | `ticketID`                    |
| `line_id`    | `lineID`                      |

**Sample response:**

```json
{
  "trim": "2.3 Premium",
  "vehicleType": "Car",
  "bodyType": "Coupe",
  "bodySubType": null,
  "doors": 2.0,
  "driveType": "FWD",
  "fuelType": "G",
  "engineBlock": "I",
  "engineCylinders": 4,
  "engineSize": 2.3,
  "engineAspiration": "N/A",
  "transType": "A",
  "transSpeeds": 4,
  "style": "2.3 Premium 2dr Coupe",
  "color": "White"
}
```

Returns `404` for vehicles that have no decoded VIN data.  The scraper marks these as
`has_details=True` with a null `VehicleDetail` row so they are not retried.

**DB table:** `vehicle_details`

---

## Rate Limiting

| Domain                               | Delay between requests |
|--------------------------------------|------------------------|
| `enterpriseservice.pullapart.com`    | 0.5 – 1.0 s (random)  |
| `inventoryservice.pullapart.com`     | 0.5 – 1.0 s (random)  |

A `429` response from either domain triggers an immediate halt and writes a
`backoff.json` file alongside the scraper. The domain will not be contacted again
until `backoff.json` is manually cleared.
