import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.vehicle import Car, Engine, Make, Model, Trim, Year


@pytest_asyncio.fixture
async def seed_vehicles(db: AsyncSession):
    yr = Year(name="2018")
    mk = Make(name="Honda", select_value="honda", start_year=1970, end_year=2025)
    mdl = Model(name="Civic", select_value="civic")
    mdl.make = mk
    trm = Trim(name="LX", select_value="lx")
    eng = Engine(name="1.5L Turbo", select_value="1-5l-turbo")
    car = Car(car_id="12345", vehicle_id="67890")
    car.year = yr; car.make = mk; car.model = mdl; car.trim = trm; car.engine = eng
    db.add_all([yr, mk, mdl, trm, eng, car])
    await db.commit()
    return {"year": yr, "make": mk, "model": mdl, "trim": trm, "engine": eng, "car": car}


async def test_get_years(client: AsyncClient, seed_vehicles):
    response = await client.get("/v1/vehicles/years")
    assert response.status_code == 200
    assert any(y["name"] == "2018" for y in response.json())


async def test_get_makes(client: AsyncClient, seed_vehicles):
    yr_id = seed_vehicles["year"].id
    response = await client.get(f"/v1/vehicles/makes?year_id={yr_id}")
    assert response.status_code == 200
    assert any(m["name"] == "Honda" for m in response.json())


async def test_get_makes_missing_param(client: AsyncClient):
    response = await client.get("/v1/vehicles/makes")
    assert response.status_code == 422


async def test_get_cars(client: AsyncClient, seed_vehicles):
    s = seed_vehicles
    response = await client.get(
        f"/v1/vehicles/cars?year_id={s['year'].id}&make_id={s['make'].id}"
        f"&model_id={s['model'].id}&trim_id={s['trim'].id}&engine_id={s['engine'].id}"
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["car_id"] == "12345"
