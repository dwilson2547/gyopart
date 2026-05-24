# Data Dictionary

Detailed description of every field returned by the Pull-A-Part API and how it maps
to the database schema.

---

## Vehicle Core Fields  (`vehicles` table)

| DB column      | API field     | Description |
|----------------|---------------|-------------|
| `vin_id`       | `vinID`       | Internal Pull-A-Part ID for the VIN record. Not the VIN itself. |
| `ticket_id`    | `ticketID`    | Unique yard ticket number assigned when the vehicle arrives. Together with `line_id` and `loc_id` this is the natural key for a vehicle. |
| `line_id`      | `lineID`      | Line item within the ticket. Usually `1`; increments if the same ticket covers multiple vehicles. |
| `loc_id`       | `locID`       | Foreign key to the `locations` table. Each Pull-A-Part yard has a distinct ID. |
| `make_id`      | `makeID`      | Foreign key to the `makes` table. |
| `model_id`     | `modelID`     | Pull-A-Part internal model ID. Not normalised into its own table — the name is stored inline. |
| `model_name`   | `modelName`   | Human-readable model string, e.g. `"TSX"`, `"Camry"`. |
| `model_year`   | `modelYear`   | 4-digit calendar year, e.g. `2004`. |
| `row`          | `row`         | Physical row number in the yard where the vehicle is parked. |
| `vin`          | `vin`         | 17-character Vehicle Identification Number. May be null for older vehicles without a decodable VIN. |
| `date_yard_on` | `dateYardOn`  | ISO 8601 datetime (no timezone, treated as UTC) when the vehicle arrived at the yard. |
| `vin_decoded_id`| `vinDecodedId`| Internal reference to the decoded-VIN database entry used to populate `vehicle_details`. |
| `has_details`  | _(derived)_   | `True` once a `vehicle_details` row has been written for this vehicle, or after a `404` was received from the extended-info endpoint (meaning no detail data is available). |
| `active`       | _(derived)_   | `True` while the vehicle appears in the current inventory feed. Set to `False` when the vehicle is sold or crushed and disappears from the API. |
| `first_seen`   | _(derived)_   | UTC datetime of the scrape run that first inserted this vehicle. |
| `last_seen`    | _(derived)_   | UTC datetime of the most recent scrape run in which this vehicle was present. |

---

## Vehicle Detail Fields  (`vehicle_details` table)

All fields come from the `VehicleExtendedInfo` endpoint.  All are nullable — not all
vehicles have a fully-decoded VIN.

| DB column           | API field          | Description |
|---------------------|--------------------|-------------|
| `trim`              | `trim`             | Trim level string, e.g. `"2.3 Premium"`, `"LX"`, `"Sport"`. |
| `vehicle_type`      | `vehicleType`      | High-level body category. Known values: `Car`, `Truck`, `SUV`, `Van`, `Minivan`. |
| `body_type`         | `bodyType`         | More specific body style. Known values: `Coupe`, `Sedan`, `Convertible`, `Hatchback`, `Wagon`, `Pickup`, `Cargo Van`, `Passenger Van`. |
| `body_sub_type`     | `bodySubType`      | Sub-classification of body type; often null. |
| `doors`             | `doors`            | Number of doors as a float (e.g. `2.0`, `4.0`). Note: API returns a float for this field. |
| `drive_type`        | `driveType`        | Drivetrain layout. Known values: `FWD` (Front-Wheel Drive), `RWD` (Rear-Wheel Drive), `AWD` (All-Wheel Drive), `4WD` (Four-Wheel Drive). |
| `fuel_type`         | `fuelType`         | Single-character fuel code. Known values: `G` = Gasoline, `D` = Diesel, `E` = Electric, `H` = Hybrid, `F` = Flex-fuel. |
| `engine_block`      | `engineBlock`      | Cylinder arrangement. Known values: `I` = Inline, `V` = V-type, `H` = Horizontally-opposed (Flat/Boxer), `R` = Rotary. |
| `engine_cylinders`  | `engineCylinders`  | Number of cylinders, e.g. `4`, `6`, `8`, `12`. |
| `engine_size`       | `engineSize`       | Displacement in litres, e.g. `2.3`, `5.0`. |
| `engine_aspiration` | `engineAspiration` | Induction method. Known values: `N/A` = Naturally Aspirated, `T` = Turbocharged, `S` = Supercharged, `TT` = Twin-Turbocharged. |
| `trans_type`        | `transType`        | Transmission type. Known values: `A` = Automatic, `M` = Manual (including CVT variants). |
| `trans_speeds`      | `transSpeeds`      | Number of forward gears, e.g. `4`, `5`, `6`, `8`, `10`. CVT is often listed as `1`. |
| `style`             | `style`            | Full free-form descriptor combining trim, doors, and body type, e.g. `"2.3 Premium 2dr Coupe"`. Useful for display. |
| `color`             | `color`            | Exterior color as a plain-English string, e.g. `"White"`, `"Silver"`, `"Blue"`. Not standardised. |
| `fetched_at`        | _(derived)_        | UTC datetime when the detail record was fetched from the API. |

---

## Location Fields  (`locations` table)

| DB column     | Typical API field | Description |
|---------------|-------------------|-------------|
| `location_id` | `locationID`      | Unique integer ID for the yard. |
| `name`        | `name` / `locationName` / `locName` | Human-readable yard name, e.g. `"Indianapolis"`. Field name varies across responses. |
| `address`     | `address`         | Street address. |
| `city`        | `city`            | City. |
| `state`       | `state`           | Two-letter US state code, e.g. `"IN"`. |
| `zip_code`    | `zip` / `postalCode` | ZIP/postal code. |
| `phone`       | `phone`           | Phone number string. |
| `lat`         | `lat` / `latitude`  | Latitude (decimal degrees). |
| `lng`         | `lng` / `longitude` | Longitude (decimal degrees). |
| `site_type_id`| `siteTypeID`      | Pull-A-Part internal site classification. `-1` in queries returns all types. |
| `active`      | _(derived)_       | Set to `False` if the location disappears from the API. |
| `first_seen`  | _(derived)_       | UTC datetime of first scrape. |
| `last_seen`   | _(derived)_       | UTC datetime of most recent scrape. |

---

## Make Fields  (`makes` table)

| DB column | API field  | Description |
|-----------|------------|-------------|
| `make_id` | `makeID`   | Unique integer make ID. |
| `name`    | `makeName` | All-caps make name, e.g. `"ACURA"`, `"HONDA"`, `"FORD"`. |

---

## Scrape Run Fields  (`scrape_runs` table)

| DB column          | Description |
|--------------------|-------------|
| `id`               | Auto-increment primary key. |
| `started_at`       | UTC start time. |
| `completed_at`     | UTC end time; null if the run failed before finishing. |
| `locations_synced` | Number of active locations at the end of the location sync phase. |
| `makes_synced`     | Number of makes synced. |
| `vehicles_added`   | New `vehicles` rows inserted this run. |
| `vehicles_removed` | Vehicles whose `active` flag was set to `False` this run (sold/crushed). |
| `details_fetched`  | Number of `vehicle_details` rows written this run. On first run this equals vehicles_added; on subsequent runs it equals only the new arrivals. |
| `success`          | `True` only if all phases completed without error. |
| `error_message`    | First 1000 characters of any unhandled exception; null on success. |

---

## Notes on NULL Values

- Any field from the `VehicleExtendedInfo` endpoint may be null for vehicles with
  partial or undecoded VINs.
- `row`, `vin`, `date_yard_on`, and `vin_decoded_id` in the core vehicle record may
  also be null depending on the vehicle's intake state.
- The scraper does not attempt to infer or backfill null values.
