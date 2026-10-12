"""
Browsing a yard: the yard list (with counts and distance from a ZIP), a yard's make/model/year facets, and a page
of its active vehicles newest arrival first. Each vehicle carries its catalogue candidates (car_id_candidates) so
the caller can link it to the parts catalogue: one candidate = exact, several = it is one of them.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from inventory_api.models import YardFacets, YardOut, YardVehicle, YardVehiclesPage

_DISTANCE = """3958.8 * 2 * asin(sqrt(
    power(sin(radians(l.lat - :lat) / 2), 2) +
    cos(radians(:lat)) * cos(radians(l.lat)) * power(sin(radians(l.lng - :lng) / 2), 2)))"""

_YARDS_SQL = """
SELECT l.id AS location_id, l.name, l.chain, l.address, l.city, l.state, l.zip_code, l.phone, l.lat, l.lng,
       l.last_seen_at,
       {distance} AS distance_miles,
       count(v.id) AS vehicle_count,
       count(v.id) FILTER (WHERE v.arrival_date >= now() - interval '7 days') AS new_this_week,
       count(v.id) FILTER (WHERE cardinality(v.car_id_candidates) > 0) AS catalogued_count
FROM locations l
LEFT JOIN vehicles v ON v.location_id = l.id AND v.is_active = true
WHERE l.is_active = true
GROUP BY l.id
"""


def list_yards(engine: Engine, lat: float | None, lng: float | None) -> list[YardOut]:
    distance = _DISTANCE if lat is not None else "NULL::float"
    sql = _YARDS_SQL.format(distance=distance)
    with engine.connect() as conn:
        rows = conn.execute(text(sql), {"lat": lat, "lng": lng}).mappings().all()
    yards = [YardOut(**r) for r in rows]
    # Nearest first when we know where the user is (yards that can't be located last), else by name.
    return sorted(yards, key=lambda y: (y.distance_miles is None, y.distance_miles or 0, y.name.lower()))


def get_yard(engine: Engine, location_id: int) -> YardOut | None:
    sql = _YARDS_SQL.format(distance="NULL::float").replace("WHERE l.is_active = true", "WHERE l.id = :id")
    with engine.connect() as conn:
        row = conn.execute(text(sql), {"id": location_id}).mappings().first()
    return YardOut(**row) if row else None


def yard_facets(engine: Engine, location_id: int) -> YardFacets:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT make, model, min(year) AS y0, max(year) AS y1, count(*) AS n
            FROM vehicles WHERE location_id = :id AND is_active = true AND make IS NOT NULL
            GROUP BY make, model ORDER BY make, model"""), {"id": location_id}).mappings().all()
    makes: dict[str, dict] = {}
    years: set[int] = set()
    for r in rows:
        m = makes.setdefault(r["make"], {"make": r["make"], "count": 0, "models": []})
        m["count"] += r["n"]
        if r["model"]:
            m["models"].append({"model": r["model"], "count": r["n"]})
        years.update(y for y in (r["y0"], r["y1"]) if y)
    return YardFacets(makes=list(makes.values()),
                      year_min=min(years) if years else None, year_max=max(years) if years else None)


def yard_vehicles(engine: Engine, location_id: int, make: str | None, model: str | None,
                  year: int | None, limit: int, offset: int) -> YardVehiclesPage:
    where = ["location_id = :id", "is_active = true"]
    params: dict = {"id": location_id, "limit": limit, "offset": offset}
    if make:
        where.append("make = :make")
        params["make"] = make
    if model:
        where.append("model = :model")
        params["model"] = model
    if year:
        where.append("year = :year")
        params["year"] = year
    cond = " AND ".join(where)
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT count(*) FROM vehicles WHERE {cond}"), params).scalar_one()
        rows = conn.execute(text(f"""
            SELECT id AS vehicle_id, year, make, model, trim, row, color, vin, arrival_date, car_id,
                   coalesce(car_id_candidates, '{{}}') AS car_id_candidates
            FROM vehicles WHERE {cond}
            ORDER BY arrival_date DESC NULLS LAST, id DESC
            LIMIT :limit OFFSET :offset"""), params).mappings().all()
    return YardVehiclesPage(total=total, limit=limit, offset=offset,
                            vehicles=[YardVehicle(**r) for r in rows])
