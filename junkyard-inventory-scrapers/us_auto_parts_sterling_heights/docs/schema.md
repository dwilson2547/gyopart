# Database Schema

SQLite database: `inventory.db`

---

## Table: `vehicles`

One row per vehicle.  Keyed on `stock_number` (the CrushYMS stock
number, e.g. `STK178314`).

Upserted on every run — `first_seen_at` is set once at initial insert
and never changed; `last_seen_at` is updated every run the vehicle
appears in the feed.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment surrogate PK |
| `stock_number` | TEXT | No | CrushYMS stock number — primary dedup key (e.g. `STK178314`) |
| `vin` | TEXT | Yes | 17-character VIN when available (most vehicles have one) |
| `year` | INTEGER | Yes | Model year |
| `make` | TEXT | Yes | Manufacturer as stored in CrushYMS (e.g. `CHEVROLET`) |
| `model` | TEXT | Yes | Model as stored in CrushYMS (e.g. `TAHOE`) |
| `hol_model` | TEXT | Yes | Normalized model description from the HOL catalog (e.g. `FORD F150 PICKUP`) |
| `color` | TEXT | Yes | Exterior colour (e.g. `BLACK`, `BLUE`) |
| `reference` | TEXT | Yes | Engine / trim notes entered by yard staff (e.g. `5.3 CD`, `3.5 TURBO`, `BURNT CF`) |
| `vehicle_row` | TEXT | Yes | Physical row number in the yard where the car is parked |
| `location` | TEXT | Yes | Yard section; typically `YARD` |
| `arrival_date` | DATETIME | Yes | Date/time the vehicle was checked into the yard (`YARD_IN_DATE` from feed) |
| `last_update` | DATETIME | Yes | Timestamp of the last CrushYMS record update (`LASTUPDATE` from feed) |
| `mileage` | INTEGER | Yes | Odometer reading as recorded by yard staff (often `1` as a placeholder) |
| `status` | TEXT | Yes | CrushYMS status code — `0` = available in yard |
| `first_seen_at` | DATETIME | No | UTC timestamp when the scraper first encountered this stock number |
| `last_seen_at` | DATETIME | No | UTC timestamp of the most recent run in which this vehicle appeared in the feed |
| `is_active` | BOOLEAN | No | `1` = vehicle is still in the current feed; `0` = no longer present (likely crushed or sold) |

### Indexes

- `stock_number` — unique index (enforces deduplication)

### Deduplication key

`stock_number` is the sole natural key.  A new stock number = a new
vehicle entering the yard.  The same stock number reappearing means the
vehicle is still present; its mutable fields (row, reference, etc.) are
updated in-place.

### Detecting removed vehicles

```sql
SELECT * FROM vehicles WHERE is_active = 0 ORDER BY last_seen_at DESC;
```

### Notes on `vin`

The public website does not expose VINs.  The CrushYMS XML feed does
include them for most vehicles (pre-1980 or salvage-title motorcycles
sometimes lack a valid VIN).  `vin` may be `NULL` for those records.

### Notes on `reference`

This is a free-text field entered by yard staff.  Common patterns:

| Example | Meaning |
|---------|---------|
| `5.3 CD` | 5.3L engine, unknown suffix |
| `3.5 TURBO` | 3.5L turbocharged engine |
| `400CI` | 400 cubic-inch displacement |
| `BURNT CF` | Fire-damaged or flood-damaged |
| `CB750` | Motorcycle model (Honda CB750) |
| `KAWASKI` | Manufacturer note (typo for KAWASAKI) |

It is useful for filtering but should not be treated as structured data.

---

## Table: `scrape_runs`

One row per scraper execution.  Used for audit and debugging.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment PK |
| `started_at` | DATETIME | No | UTC time the run began |
| `completed_at` | DATETIME | Yes | UTC time the run finished (NULL if still running or crashed) |
| `total_in_feed` | INTEGER | Yes | Total `<ASSET>` records returned by the XML feed |
| `new_vehicles` | INTEGER | Yes | Vehicles inserted for the first time this run |
| `updated_vehicles` | INTEGER | Yes | Existing vehicles whose fields were refreshed |
| `removed_vehicles` | INTEGER | Yes | Vehicles marked `is_active = 0` because they disappeared from the feed |
| `success` | BOOLEAN | Yes | `1` if the run completed without error |
| `error_message` | TEXT | Yes | First 500 characters of the exception message on failure |

### Useful queries

```sql
-- Last 10 runs
SELECT id, started_at, total_in_feed, new_vehicles, removed_vehicles, success
FROM scrape_runs
ORDER BY id DESC
LIMIT 10;

-- How many vehicles are currently active?
SELECT COUNT(*) FROM vehicles WHERE is_active = 1;

-- Vehicles added in the last 7 days
SELECT stock_number, year, make, model, color, reference, arrival_date
FROM vehicles
WHERE is_active = 1
  AND first_seen_at >= datetime('now', '-7 days')
ORDER BY first_seen_at DESC;

-- Find all Hondas currently in the yard
SELECT stock_number, year, model, color, reference, vehicle_row
FROM vehicles
WHERE make = 'HONDA' AND is_active = 1
ORDER BY year DESC;
```

---

## Feed source mapping

| XML tag | DB column | Notes |
|---------|-----------|-------|
| `STOCKNUMBER` | `stock_number` | Primary dedup key |
| `VIN` | `vin` | |
| `iYEAR` | `year` | Parsed to INTEGER |
| `MAKE` | `make` | |
| `MODEL` | `model` | |
| `HOL_MODEL` | `hol_model` | HOL normalised model name |
| `COLOR` | `color` | |
| `REFERENCE` | `reference` | Free-text engine/trim notes |
| `VEHICLE_ROW` | `vehicle_row` | |
| `LOCATION` | `location` | |
| `YARD_IN_DATE` | `arrival_date` | ISO datetime, e.g. `2026-04-29T10:31:38.923` |
| `LASTUPDATE` | `last_update` | `MM/DD/YYYY HH:MM:SS AM/PM` format |
| `MILEAGE` | `mileage` | Parsed to INTEGER |
| `iSTATUS` | `status` | `"0"` = available |
