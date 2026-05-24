# Database Schema

The scraper uses a single SQLite file (`pull_a_part.db`) managed by SQLAlchemy.
All timestamps are stored in **naive UTC**.

---

## Entity Relationship Diagram

```
scrape_runs
  id (PK)
  started_at
  completed_at
  locations_synced
  makes_synced
  vehicles_added
  vehicles_removed
  details_fetched
  success
  error_message

locations (1) ──< vehicles (N)
  location_id (PK)           id (PK)
  name                       vin_id
  address                    ticket_id  ─┐  unique together
  city                       line_id    ─┤  (uq_vehicle)
  state                      loc_id  FK─┘
  zip_code                   make_id FK ──── makes
  phone                      model_id
  lat / lng                  model_name
  site_type_id               model_year
  active                     row
  first_seen / last_seen     vin
                             date_yard_on
makes (1) ──< vehicles (N)   vin_decoded_id
  make_id (PK)               has_details
  name                       active
                             first_seen / last_seen

vehicles (1) ──── vehicle_details (0..1)
                   vehicle_id (PK, FK → vehicles.id)
                   trim
                   vehicle_type
                   body_type / body_sub_type
                   doors
                   drive_type
                   fuel_type
                   engine_block / engine_cylinders
                   engine_size / engine_aspiration
                   trans_type / trans_speeds
                   style
                   color
                   fetched_at
```

---

## Tables

### `locations`

| Column        | Type         | Notes                                          |
|---------------|--------------|------------------------------------------------|
| location_id   | INTEGER PK   | Pull-A-Part internal location ID               |
| name          | VARCHAR(200) |                                                |
| address       | VARCHAR(500) | Street address, nullable                       |
| city          | VARCHAR(100) | nullable                                       |
| state         | VARCHAR(10)  | State abbreviation, nullable                   |
| zip_code      | VARCHAR(20)  | nullable                                       |
| phone         | VARCHAR(50)  | nullable                                       |
| lat           | FLOAT        | Latitude, nullable                             |
| lng           | FLOAT        | Longitude, nullable                            |
| site_type_id  | INTEGER      | From API `siteTypeID`, nullable                |
| active        | BOOLEAN      | False if location disappeared from API         |
| first_seen    | DATETIME     | UTC timestamp of first scrape                  |
| last_seen     | DATETIME     | UTC timestamp of most recent scrape            |

---

### `makes`

| Column   | Type         | Notes                       |
|----------|--------------|-----------------------------|
| make_id  | INTEGER PK   | Pull-A-Part make ID         |
| name     | VARCHAR(200) | e.g. `"ACURA"`, `"HONDA"`   |

---

### `vehicles`

| Column         | Type         | Notes                                                    |
|----------------|--------------|----------------------------------------------------------|
| id             | INTEGER PK   | Auto-increment surrogate key                             |
| vin_id         | INTEGER      | API `vinID`, nullable                                    |
| ticket_id      | INTEGER      | API `ticketID`, indexed                                  |
| line_id        | INTEGER      | API `lineID`                                             |
| loc_id         | INTEGER FK   | → `locations.location_id`, indexed                       |
| make_id        | INTEGER FK   | → `makes.make_id`                                        |
| model_id       | INTEGER      | API `modelID`, nullable                                  |
| model_name     | VARCHAR(200) | API `modelName`, nullable                                |
| model_year     | INTEGER      | 4-digit year, nullable                                   |
| row            | INTEGER      | Physical yard row number, nullable                       |
| vin            | VARCHAR(50)  | 17-char VIN, nullable                                    |
| date_yard_on   | DATETIME     | When the vehicle arrived at the yard                     |
| vin_decoded_id | INTEGER      | Internal decoded-VIN reference, nullable                 |
| has_details    | BOOLEAN      | True once `vehicle_details` row exists (or 404 received) |
| active         | BOOLEAN      | False once vehicle leaves the yard                       |
| first_seen     | DATETIME     | UTC timestamp of first scrape                            |
| last_seen      | DATETIME     | UTC timestamp of most recent scrape                      |

**Unique constraint:** `(ticket_id, line_id, loc_id)` — prevents duplicates across runs.

---

### `vehicle_details`

| Column            | Type         | Notes                                          |
|-------------------|--------------|------------------------------------------------|
| vehicle_id        | INTEGER PK   | FK → `vehicles.id`                             |
| trim              | VARCHAR(200) | e.g. `"2.3 Premium"`, nullable                 |
| vehicle_type      | VARCHAR(100) | `"Car"`, `"Truck"`, `"SUV"`, `"Van"`, nullable |
| body_type         | VARCHAR(100) | `"Coupe"`, `"Sedan"`, `"Pickup"`, etc.         |
| body_sub_type     | VARCHAR(100) | nullable                                       |
| doors             | FLOAT        | Number of doors (e.g. `2.0`, `4.0`)            |
| drive_type        | VARCHAR(50)  | `"FWD"`, `"RWD"`, `"AWD"`, `"4WD"`            |
| fuel_type         | VARCHAR(50)  | See data dictionary for code meanings          |
| engine_block      | VARCHAR(10)  | `"I"`, `"V"`, `"H"` — cylinder arrangement    |
| engine_cylinders  | INTEGER      | e.g. `4`, `6`, `8`                             |
| engine_size       | FLOAT        | Displacement in litres, e.g. `2.3`             |
| engine_aspiration | VARCHAR(50)  | `"N/A"`, `"T"`, `"S"` — see data dictionary   |
| trans_type        | VARCHAR(10)  | `"A"` = Automatic, `"M"` = Manual              |
| trans_speeds      | INTEGER      | Gear count, e.g. `4`, `5`, `6`, `8`           |
| style             | VARCHAR(200) | Full descriptor, e.g. `"2.3 Premium 2dr Coupe"`|
| color             | VARCHAR(100) | Exterior color string, nullable                |
| fetched_at        | DATETIME     | UTC timestamp when detail was fetched          |

---

### `scrape_runs`

| Column           | Type          | Notes                                             |
|------------------|---------------|---------------------------------------------------|
| id               | INTEGER PK    | Auto-increment                                    |
| started_at       | DATETIME      | UTC start of run                                  |
| completed_at     | DATETIME      | UTC end of run (null if failed mid-run)           |
| locations_synced | INTEGER       | Count of active locations at end of sync          |
| makes_synced     | INTEGER       | Count of makes synced                             |
| vehicles_added   | INTEGER       | New vehicles inserted this run                    |
| vehicles_removed | INTEGER       | Vehicles marked inactive this run                 |
| details_fetched  | INTEGER       | `vehicle_details` rows written this run           |
| success          | BOOLEAN       | True only on clean completion                     |
| error_message    | VARCHAR(1000) | First 1000 chars of exception message on failure  |

---

## Useful Queries

```sql
-- All active vehicles with full details at a specific location
SELECT v.*, d.*
FROM vehicles v
JOIN vehicle_details d ON d.vehicle_id = v.id
WHERE v.loc_id = 18 AND v.active = 1;

-- Vehicles added in the most recent run
SELECT v.model_year, v.model_name, l.name AS location
FROM vehicles v
JOIN locations l ON l.location_id = v.loc_id
WHERE v.first_seen = (SELECT MAX(started_at) FROM scrape_runs WHERE success = 1);

-- Vehicles still missing details
SELECT COUNT(*) FROM vehicles WHERE active = 1 AND has_details = 0;

-- Inventory count by location
SELECT l.name, COUNT(*) AS vehicle_count
FROM vehicles v
JOIN locations l ON l.location_id = v.loc_id
WHERE v.active = 1
GROUP BY l.location_id
ORDER BY vehicle_count DESC;

-- Run history
SELECT id, started_at, completed_at,
       vehicles_added, vehicles_removed, details_fetched, success
FROM scrape_runs
ORDER BY id DESC
LIMIT 20;
```
