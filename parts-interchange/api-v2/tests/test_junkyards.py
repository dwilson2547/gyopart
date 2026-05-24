import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.junkyard import Junkyard, JunkyardInventory
from src.models.parts import Manufacturer, Part
from src.models.vehicle import Car, Engine, Make, Model, Trim, Year, car_parts


@pytest_asyncio.fixture
async def seed_junkyard(db: AsyncSession):
    mfr = Manufacturer(name="Honda2", base_url="https://honda.example.com")
    yr = Year(name="2019")
    mk = Make(name="Honda", select_value="honda2", start_year=1970, end_year=2025)
    mdl = Model(name="Accord", select_value="accord")
    mdl.make = mk
    trm = Trim(name="Sport", select_value="sport")
    eng = Engine(name="1.5L", select_value="1-5l")
    car = Car(car_id="jy1", vehicle_id="jy2")
    car.year = yr; car.make = mk; car.model = mdl; car.trim = trm; car.engine = eng
    part = Part(part_number="AXLE-001", title="Axle Shaft")
    part.manufacturer = mfr
    db.add_all([mfr, yr, mk, mdl, trm, eng, car, part])
    await db.flush()
    await db.execute(car_parts.insert().values(car_id=car.id, part_id=part.id))
    jy = Junkyard(name="Pick-A-Part", city="Los Angeles", state="CA", lat=34.05, lng=-118.24, active=True)
    inv = JunkyardInventory(year="2019", make_name="honda", model_name="accord", junkyard=jy)
    db.add_all([jy, inv])
    await db.commit()
    return {"part": part, "junkyard": jy}


async def test_junkyard_search_by_part(client: AsyncClient, seed_junkyard):
    part_id = seed_junkyard["part"].id
    response = await client.get(f"/v1/junkyards?part_id={part_id}&page=1&per_page=25")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["junkyard"]["name"] == "Pick-A-Part"


async def test_junkyard_search_with_proximity(client: AsyncClient, seed_junkyard):
    part_id = seed_junkyard["part"].id
    response = await client.get(f"/v1/junkyards?part_id={part_id}&lat=34.05&lng=-118.24&page=1&per_page=25")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["distance_miles"] is not None
    assert data["items"][0]["distance_miles"] < 1.0


async def test_junkyard_search_missing_part_param(client: AsyncClient):
    response = await client.get("/v1/junkyards")
    assert response.status_code == 422
