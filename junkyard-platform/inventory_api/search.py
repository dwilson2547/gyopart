from __future__ import annotations

from collections import defaultdict

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from inventory_api.models import LocationResult, VehicleResult

_HAVERSINE_SQL = text("""
SELECT *
FROM (
    SELECT
        l.id                AS location_id,
        l.name              AS name,
        l.address           AS address,
        l.city              AS city,
        l.state             AS state,
        l.zip_code          AS zip_code,
        l.phone             AS phone,
        3958.8 * 2 * asin(
            sqrt(
                power(sin(radians(l.lat - :lat) / 2), 2) +
                cos(radians(:lat)) * cos(radians(l.lat)) *
                power(sin(radians(l.lng - :lng) / 2), 2)
            )
        )                   AS distance_miles,
        v.id                AS vehicle_id,
        v.year              AS year,
        v.make              AS make,
        v.model             AS model,
        v.trim              AS trim,
        v.row               AS row,
        v.car_id            AS car_id
    FROM locations l
    JOIN vehicles v ON v.location_id = l.id
    WHERE l.is_active = true
      AND v.is_active = true
      AND l.lat IS NOT NULL
      AND l.lng IS NOT NULL
      AND v.car_id_resolved = true
      AND v.car_id IN :car_ids
) sub
WHERE distance_miles <= :radius_miles
ORDER BY distance_miles ASC
""").bindparams(bindparam("car_ids", expanding=True))


def search_inventory(
    engine: Engine,
    car_ids: list[int],
    lat: float,
    lng: float,
    radius_miles: float,
) -> list[LocationResult]:
    if not car_ids:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            _HAVERSINE_SQL,
            {"lat": lat, "lng": lng, "radius_miles": radius_miles, "car_ids": tuple(car_ids)},
        ).mappings().all()

    locations: dict[int, dict] = {}
    vehicles_by_loc: dict[int, list[VehicleResult]] = defaultdict(list)

    for row in rows:
        loc_id = row["location_id"]
        if loc_id not in locations:
            locations[loc_id] = {
                "location_id": loc_id,
                "name": row["name"],
                "address": row["address"],
                "city": row["city"],
                "state": row["state"],
                "zip_code": row["zip_code"],
                "phone": row["phone"],
                "distance_miles": row["distance_miles"],
            }
        vehicles_by_loc[loc_id].append(VehicleResult(
            vehicle_id=row["vehicle_id"],
            year=row["year"],
            make=row["make"],
            model=row["model"],
            trim=row["trim"],
            row=row["row"],
            car_id=row["car_id"],
        ))

    return [
        LocationResult(**loc_data, matching_vehicles=vehicles_by_loc[loc_id])
        for loc_id, loc_data in locations.items()
    ]
