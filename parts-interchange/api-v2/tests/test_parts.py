import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.parts import Manufacturer, Part
from src.models.vehicle import Car, Engine, Make, Model, Trim, Year, car_parts


@pytest_asyncio.fixture
async def seed_parts(db: AsyncSession):
    mfr = Manufacturer(name="Acura", base_url="https://acura.example.com")
    yr = Year(name="2020")
    mk = Make(name="Acura", select_value="acura", start_year=1986, end_year=2025)
    mdl = Model(name="TLX", select_value="tlx")
    mdl.make = mk
    trm = Trim(name="Base", select_value="base")
    eng = Engine(name="2.0L", select_value="2-0l")
    car = Car(car_id="abc", vehicle_id="def")
    car.year = yr; car.make = mk; car.model = mdl; car.trim = trm; car.engine = eng
    part = Part(part_number="44018-TGV-A01", title="Driveshaft", positions=["Front", "Left"])
    part.manufacturer = mfr
    db.add_all([mfr, yr, mk, mdl, trm, eng, car, part])
    await db.flush()
    await db.execute(car_parts.insert().values(car_id=car.id, part_id=part.id))
    await db.commit()
    return {"car": car, "part": part}


async def test_get_parts_for_car(client: AsyncClient, seed_parts):
    car_id = seed_parts["car"].id
    response = await client.get(f"/v1/parts?car_id={car_id}&page=1&per_page=25")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["part_number"] == "44018-TGV-A01"


async def test_get_part_detail(client: AsyncClient, seed_parts):
    part_id = seed_parts["part"].id
    response = await client.get(f"/v1/parts/{part_id}")
    assert response.status_code == 200
    assert response.json()["part_number"] == "44018-TGV-A01"


async def test_get_compatible_cars(client: AsyncClient, seed_parts):
    part_id = seed_parts["part"].id
    response = await client.get(f"/v1/parts/{part_id}/compatible-cars?page=1&per_page=25")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["car_id"] == "abc"


async def test_parts_filter(client: AsyncClient, seed_parts):
    car_id = seed_parts["car"].id
    response = await client.get(f"/v1/parts?car_id={car_id}&page=1&per_page=25&filter=Driveshaft")
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_part_not_found(client: AsyncClient):
    response = await client.get("/v1/parts/999999")
    assert response.status_code == 404


async def test_applications_html_stripped(client: AsyncClient, seed_parts, db: AsyncSession):
    part = seed_parts["part"]
    part.applications = "<b>Body Styles:</b> Sedan."
    await db.commit()
    response = await client.get(f"/v1/parts/{part.id}")
    assert "<b>" not in (response.json().get("applications") or "")
