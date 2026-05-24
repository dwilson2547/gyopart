# Phase 6 — API v3 + UI v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A production-ready FastAPI backend (`gyopart-api`) and React/Vite frontend (`gyopart-ui`) that let users pick a vehicle, browse its parts, and find nearby junkyards with matching inventory in stock.

**Architecture:** `gyopart-api` (port 8200) connects to the `parts_interchange` Postgres DB for vehicle/parts data, and calls the Phase 4 inventory search API via HTTP for junkyard proximity results — it does not query the junkyard DB directly. `gyopart-ui` is a React/Vite SPA with a left rail (vehicle picker → parts list) and a right panel (yard results), using a zip code for location input. Both `api-v2` and `ui-v2` are POC directories — do not modify them.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (sync), psycopg2-binary, httpx, Pydantic v2, pydantic-settings, pytest — React 18, Vite, TypeScript, Tailwind CSS v4, axios, lucide-react.

> **User constraint:** NO git commits ever.

> **Phase 1.5 note (not part of this phase):** Before building new scrapers, implement a `BaseScraper` abstract class in `junkyard_common` with `run()` as an abstract method and all `main()` boilerplate (ScrapeRun creation, stats tracking, error/success recording) handled by the base. Each scraper's `main()` becomes `BaseScraper.main()` and the scraper subclass only overrides `run()`. This normalizes the interface across the entire fleet.

---

## Env Vars

| Variable | Service | Description |
|---|---|---|
| `PARTS_DATABASE_URL` | gyopart-api | PostgreSQL DSN for parts_interchange DB |
| `INVENTORY_API_URL` | gyopart-api | Base URL for Phase 4 inventory search service (e.g. `http://localhost:8000`) |
| `INVENTORY_API_TIMEOUT` | gyopart-api | HTTP timeout seconds (default: `10.0`) |
| `CORS_ORIGINS` | gyopart-api | Comma-separated allowed origins (default: `http://localhost:5173`) |
| `VITE_API_BASE_URL` | gyopart-ui | gyopart-api base URL (e.g. `http://localhost:8200`) |

---

## File Map

### gyopart-api

| Action | Path | Responsibility |
|---|---|---|
| Create | `gyopart-api/requirements.txt` | Python deps |
| Create | `gyopart-api/pytest.ini` | pytest config (sets pythonpath) |
| Create | `gyopart-api/src/__init__.py` | Package marker |
| Create | `gyopart-api/src/config.py` | pydantic-settings (env vars) |
| Create | `gyopart-api/src/db.py` | Engine, `get_db()` dependency, `Base` |
| Create | `gyopart-api/src/models.py` | SQLAlchemy ORM for parts_interchange tables |
| Create | `gyopart-api/src/schemas.py` | Pydantic response models |
| Create | `gyopart-api/src/routers/__init__.py` | Package marker |
| Create | `gyopart-api/src/routers/vehicles.py` | `/v1/vehicles/*` — cascading picker endpoints |
| Create | `gyopart-api/src/routers/parts.py` | `/v1/parts/*` — list, detail, compatible-cars |
| Create | `gyopart-api/src/routers/search.py` | `/v1/search` — resolves car_ids → calls inventory API |
| Create | `gyopart-api/src/main.py` | FastAPI app, CORS, router includes |
| Create | `gyopart-api/tests/__init__.py` | Package marker |
| Create | `gyopart-api/tests/conftest.py` | TestClient fixture with mocked DB dependency |
| Create | `gyopart-api/tests/test_vehicles.py` | Vehicle picker route tests |
| Create | `gyopart-api/tests/test_parts.py` | Parts route tests |
| Create | `gyopart-api/tests/test_search.py` | Search route tests (mocks httpx) |

### gyopart-ui

| Action | Path | Responsibility |
|---|---|---|
| Create | `gyopart-ui/` | Vite scaffold via `npm create vite` |
| Create | `gyopart-ui/src/types.ts` | All shared TypeScript types |
| Create | `gyopart-ui/src/api.ts` | Typed axios API client |
| Create | `gyopart-ui/src/context/AppContext.tsx` | Global state: selectedVehicle, activePart, zip, results |
| Create | `gyopart-ui/src/hooks/useVehicleTree.ts` | Cascading vehicle picker data + selection state |
| Create | `gyopart-ui/src/components/TopBar.tsx` | App header |
| Create | `gyopart-ui/src/components/VehiclePicker.tsx` | Year/make/model/trim/engine selects |
| Create | `gyopart-ui/src/components/PartsList.tsx` | Scrollable filtered parts list |
| Create | `gyopart-ui/src/components/ZipInput.tsx` | Zip + radius input with search trigger |
| Create | `gyopart-ui/src/components/YardCard.tsx` | Single yard result with matching vehicles table |
| Create | `gyopart-ui/src/components/JunkyardResults.tsx` | Right panel: zip input + yard cards |
| Modify | `gyopart-ui/src/App.tsx` | Layout: left rail / right panel |
| Modify | `gyopart-ui/src/main.tsx` | Wrap app with AppProvider |

---

### Task 1: gyopart-api Scaffold — Requirements, Config, DB, Models

**Files:**
- Create: `gyopart-api/requirements.txt`
- Create: `gyopart-api/pytest.ini`
- Create: `gyopart-api/src/__init__.py`
- Create: `gyopart-api/src/config.py`
- Create: `gyopart-api/src/db.py`
- Create: `gyopart-api/src/models.py`
- Create: `gyopart-api/src/schemas.py`
- Create: `gyopart-api/tests/__init__.py`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p /home/daniel/documents/workspace/gyopart/gyopart-api/src/routers
mkdir -p /home/daniel/documents/workspace/gyopart/gyopart-api/tests
touch /home/daniel/documents/workspace/gyopart/gyopart-api/src/__init__.py
touch /home/daniel/documents/workspace/gyopart/gyopart-api/src/routers/__init__.py
touch /home/daniel/documents/workspace/gyopart/gyopart-api/tests/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

Create `gyopart-api/requirements.txt`:

```
fastapi>=0.111
uvicorn[standard]>=0.29
sqlalchemy>=2.0
psycopg2-binary>=2.9
pydantic>=2.0
pydantic-settings>=2.0
httpx>=0.27
pytest>=8.0
pytest-mock>=3.0
```

- [ ] **Step 3: Create `pytest.ini`**

Create `gyopart-api/pytest.ini`:

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Install requirements**

```bash
pip install -r /home/daniel/documents/workspace/gyopart/gyopart-api/requirements.txt 2>&1 | tail -5
```

- [ ] **Step 5: Create `src/config.py`**

Create `gyopart-api/src/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    parts_database_url: str
    inventory_api_url: str = "http://localhost:8000"
    inventory_api_timeout: float = 10.0
    cors_origins: str = "http://localhost:5173"

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 6: Create `src/db.py`**

Create `gyopart-api/src/db.py`:

```python
from __future__ import annotations

from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from src.config import settings
        _engine = create_engine(settings.parts_database_url, pool_pre_ping=True)
    return _engine


def get_db() -> Generator[Session, None, None]:
    with Session(_get_engine()) as session:
        yield session


DbDep = Annotated[Session, Depends(get_db)]
```

- [ ] **Step 7: Create `src/models.py`**

Create `gyopart-api/src/models.py`:

```python
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text

from src.db import Base

car_parts = Table(
    "car_parts",
    Base.metadata,
    Column("car_id", Integer, ForeignKey("car.id"), primary_key=True),
    Column("part_id", Integer, ForeignKey("part.id"), primary_key=True),
)


class Year(Base):
    __tablename__ = "year"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Make(Base):
    __tablename__ = "make"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Model(Base):
    __tablename__ = "model"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    make_id = Column(Integer, ForeignKey("make.id"))


class Trim(Base):
    __tablename__ = "trim"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Engine(Base):
    __tablename__ = "engine"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))


class Car(Base):
    __tablename__ = "car"
    id = Column(Integer, primary_key=True)
    year_id = Column(Integer, ForeignKey("year.id"))
    make_id = Column(Integer, ForeignKey("make.id"))
    model_id = Column(Integer, ForeignKey("model.id"))
    trim_id = Column(Integer, ForeignKey("trim.id"))
    engine_id = Column(Integer, ForeignKey("engine.id"))


class Part(Base):
    __tablename__ = "part"
    id = Column(Integer, primary_key=True)
    title = Column(String(500))
    part_number = Column(String(200))
    description = Column(Text)
    other_names = Column(String)
```

- [ ] **Step 8: Create `src/schemas.py`**

Create `gyopart-api/src/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class YearOut(_OrmBase):
    id: int
    name: str


class MakeOut(_OrmBase):
    id: int
    name: str


class ModelOut(_OrmBase):
    id: int
    name: str
    make_id: int


class TrimOut(_OrmBase):
    id: int
    name: str


class EngineOut(_OrmBase):
    id: int
    name: str


class CarOut(_OrmBase):
    id: int
    year_id: int
    make_id: int
    model_id: int
    trim_id: int
    engine_id: int


class PartOut(_OrmBase):
    id: int
    title: str | None
    part_number: str | None
    description: str | None
    other_names: str | None


class PagedPartsResponse(BaseModel):
    items: list[PartOut]
    total: int
    page: int
    per_page: int


class VehicleResult(BaseModel):
    vehicle_id: int
    year: int | None
    make: str | None
    model: str | None
    trim: str | None
    row: str | None
    car_id: int | None


class YardResult(BaseModel):
    location_id: int
    name: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    distance_miles: float
    matching_vehicles: list[VehicleResult]


class SearchResponse(BaseModel):
    results: list[YardResult]
```

- [ ] **Step 9: Verify imports work**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -c "from src.models import Year, Make, Car, Part; from src.schemas import SearchResponse; print('OK')"
```

Expected: `OK`

---

### Task 2: gyopart-api Vehicle Picker Routes + Tests

**Files:**
- Create: `gyopart-api/src/routers/vehicles.py`
- Create: `gyopart-api/src/main.py`
- Create: `gyopart-api/tests/conftest.py`
- Create: `gyopart-api/tests/test_vehicles.py`

- [ ] **Step 1: Write failing vehicle tests**

Create `gyopart-api/tests/conftest.py`:

```python
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.main import app
from src.db import get_db


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

Create `gyopart-api/tests/test_vehicles.py`:

```python
from unittest.mock import MagicMock


def _obj(**kwargs):
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def test_get_years(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _obj(id=1, name="2022"), _obj(id=2, name="2021"),
    ]
    resp = client.get("/v1/vehicles/years")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "2022"


def test_get_makes_requires_year_id(client, mock_db):
    resp = client.get("/v1/vehicles/makes")
    assert resp.status_code == 422


def test_get_makes(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="Toyota")]
    resp = client.get("/v1/vehicles/makes?year_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Toyota"


def test_get_models(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="Camry", make_id=1)]
    resp = client.get("/v1/vehicles/models?year_id=1&make_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Camry"


def test_get_trims(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="LE")]
    resp = client.get("/v1/vehicles/trims?year_id=1&make_id=1&model_id=1")
    assert resp.status_code == 200


def test_get_engines(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_obj(id=1, name="2.5L 4-cyl")]
    resp = client.get("/v1/vehicles/engines?year_id=1&make_id=1&model_id=1&trim_id=1")
    assert resp.status_code == 200


def test_get_cars(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _obj(id=99, year_id=1, make_id=1, model_id=1, trim_id=1, engine_id=1)
    ]
    resp = client.get("/v1/vehicles/cars?year_id=1&make_id=1&model_id=1&trim_id=1&engine_id=1")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 99


def test_get_cars_requires_all_params(client, mock_db):
    resp = client.get("/v1/vehicles/cars?year_id=1&make_id=1")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/test_vehicles.py -v 2>&1 | head -20
```

Expected: `ImportError` — `src.main` doesn't exist yet.

- [ ] **Step 3: Create `src/routers/vehicles.py`**

Create `gyopart-api/src/routers/vehicles.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.db import DbDep
from src.models import Car, Engine, Make, Model, Trim, Year
from src.schemas import CarOut, EngineOut, MakeOut, ModelOut, TrimOut, YearOut

router = APIRouter(prefix="/v1/vehicles", tags=["vehicles"])


@router.get("/years", response_model=list[YearOut])
def get_years(db: DbDep):
    return db.execute(select(Year).order_by(Year.name.desc())).scalars().all()


@router.get("/makes", response_model=list[MakeOut])
def get_makes(db: DbDep, year_id: int = Query(...)):
    sub = select(Car.make_id).where(Car.year_id == year_id).distinct()
    return db.execute(select(Make).where(Make.id.in_(sub)).order_by(Make.name)).scalars().all()


@router.get("/models", response_model=list[ModelOut])
def get_models(db: DbDep, year_id: int = Query(...), make_id: int = Query(...)):
    sub = select(Car.model_id).where(Car.year_id == year_id, Car.make_id == make_id).distinct()
    return db.execute(select(Model).where(Model.id.in_(sub)).order_by(Model.name)).scalars().all()


@router.get("/trims", response_model=list[TrimOut])
def get_trims(
    db: DbDep,
    year_id: int = Query(...),
    make_id: int = Query(...),
    model_id: int = Query(...),
):
    sub = select(Car.trim_id).where(
        Car.year_id == year_id, Car.make_id == make_id, Car.model_id == model_id
    ).distinct()
    return db.execute(select(Trim).where(Trim.id.in_(sub)).order_by(Trim.name)).scalars().all()


@router.get("/engines", response_model=list[EngineOut])
def get_engines(
    db: DbDep,
    year_id: int = Query(...),
    make_id: int = Query(...),
    model_id: int = Query(...),
    trim_id: int = Query(...),
):
    sub = select(Car.engine_id).where(
        Car.year_id == year_id, Car.make_id == make_id,
        Car.model_id == model_id, Car.trim_id == trim_id,
    ).distinct()
    return db.execute(select(Engine).where(Engine.id.in_(sub)).order_by(Engine.name)).scalars().all()


@router.get("/cars", response_model=list[CarOut])
def get_cars(
    db: DbDep,
    year_id: int = Query(...),
    make_id: int = Query(...),
    model_id: int = Query(...),
    trim_id: int = Query(...),
    engine_id: int = Query(...),
):
    return db.execute(
        select(Car).where(
            Car.year_id == year_id, Car.make_id == make_id,
            Car.model_id == model_id, Car.trim_id == trim_id,
            Car.engine_id == engine_id,
        )
    ).scalars().all()
```

- [ ] **Step 4: Create minimal `src/main.py`**

Create `gyopart-api/src/main.py`:

```python
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import vehicles

app = FastAPI(title="Parts Interchange API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(vehicles.router)
```

- [ ] **Step 5: Run vehicle tests**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/test_vehicles.py -v 2>&1
```

Expected: 8 PASSED.

---

### Task 3: gyopart-api Parts Routes + Tests

**Files:**
- Create: `gyopart-api/src/routers/parts.py`
- Modify: `gyopart-api/src/main.py` (add parts router)
- Create: `gyopart-api/tests/test_parts.py`

- [ ] **Step 1: Write failing parts tests**

Create `gyopart-api/tests/test_parts.py`:

```python
from unittest.mock import MagicMock


def _part(id=1, title="Engine Air Filter", part_number="A-100", description=None, other_names=None):
    m = MagicMock()
    m.id = id
    m.title = title
    m.part_number = part_number
    m.description = description
    m.other_names = other_names
    return m


def test_get_parts_requires_car_id(client, mock_db):
    resp = client.get("/v1/parts")
    assert resp.status_code == 422


def test_get_parts(client, mock_db):
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [_part()]
    mock_db.execute.side_effect = [count_result, items_result]
    resp = client.get("/v1/parts?car_id=99")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Engine Air Filter"
    assert data["page"] == 1


def test_get_part_by_id(client, mock_db):
    mock_db.get.return_value = _part(id=5, title="Alternator")
    resp = client.get("/v1/parts/5")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Alternator"


def test_get_part_not_found(client, mock_db):
    mock_db.get.return_value = None
    resp = client.get("/v1/parts/999")
    assert resp.status_code == 404


def test_get_compatible_car_ids(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    resp = client.get("/v1/parts/5/compatible-cars")
    assert resp.status_code == 200
    assert resp.json() == [1, 2, 3]


def test_get_parts_filter_param_accepted(client, mock_db):
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [count_result, items_result]
    resp = client.get("/v1/parts?car_id=1&filter=filter&page=2")
    assert resp.status_code == 200
    assert resp.json()["page"] == 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/test_parts.py::test_get_parts_requires_car_id -v 2>&1 | head -10
```

Expected: `404` (route not registered yet).

- [ ] **Step 3: Create `src/routers/parts.py`**

Create `gyopart-api/src/routers/parts.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from src.db import DbDep
from src.models import Part, car_parts
from src.schemas import PagedPartsResponse, PartOut

router = APIRouter(prefix="/v1/parts", tags=["parts"])


@router.get("", response_model=PagedPartsResponse)
def get_parts(
    db: DbDep,
    car_id: int = Query(...),
    filter: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
):
    q = (
        select(Part)
        .join(car_parts, car_parts.c.part_id == Part.id)
        .where(car_parts.c.car_id == car_id)
    )
    if filter:
        q = q.where(Part.title.icontains(filter) | Part.part_number.icontains(filter))
    q = q.order_by(Part.part_number)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    items = db.execute(q.offset((page - 1) * per_page).limit(per_page)).scalars().all()
    return PagedPartsResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/{part_id}", response_model=PartOut)
def get_part(part_id: int, db: DbDep):
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="part not found")
    return part


@router.get("/{part_id}/compatible-cars", response_model=list[int])
def get_compatible_car_ids(part_id: int, db: DbDep):
    return db.execute(
        select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    ).scalars().all()
```

- [ ] **Step 4: Register parts router in `main.py`**

Add to `gyopart-api/src/main.py`:

```python
from src.routers import parts, vehicles

# ...
app.include_router(vehicles.router)
app.include_router(parts.router)
```

The complete updated imports section:
```python
from src.routers import parts, vehicles
```

And the includes at the bottom:
```python
app.include_router(vehicles.router)
app.include_router(parts.router)
```

- [ ] **Step 5: Run parts tests**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/test_parts.py -v 2>&1
```

Expected: 6 PASSED.

---

### Task 4: gyopart-api Search Route + Startup Smoke Test

**Files:**
- Create: `gyopart-api/src/routers/search.py`
- Modify: `gyopart-api/src/main.py` (add search router)
- Create: `gyopart-api/tests/test_search.py`

- [ ] **Step 1: Write failing search tests**

Create `gyopart-api/tests/test_search.py`:

```python
import httpx
from unittest.mock import MagicMock, patch


def _yard():
    return {
        "location_id": 1, "name": "Pick-n-Pull Detroit", "address": "123 Main St",
        "city": "Detroit", "state": "MI", "zip_code": "48201",
        "phone": "555-1234", "distance_miles": 12.5,
        "matching_vehicles": [
            {"vehicle_id": 42, "year": 2018, "make": "Toyota", "model": "Camry",
             "trim": "LE", "row": "A14", "car_id": 99}
        ],
    }


def test_search_requires_part_id_and_zip(client, mock_db):
    resp = client.get("/v1/search")
    assert resp.status_code == 422


def test_search_zip_must_be_5_chars(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1]
    resp = client.get("/v1/search?part_id=1&zip=123")
    assert resp.status_code == 422


def test_search_no_compatible_cars_returns_empty(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    resp = client.get("/v1/search?part_id=1&zip=48093")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_calls_inventory_api_with_car_ids(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 2, 3]
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [_yard()]}
    mock_resp.raise_for_status = MagicMock()

    with patch("src.routers.search.httpx.get", return_value=mock_resp) as mock_get:
        resp = client.get("/v1/search?part_id=1&zip=48093&radius_miles=25")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Pick-n-Pull Detroit"
    assert data["results"][0]["distance_miles"] == 12.5
    assert data["results"][0]["matching_vehicles"][0]["make"] == "Toyota"

    params = mock_get.call_args.kwargs["params"]
    assert params["car_ids"] == "1,2,3"
    assert params["zip"] == "48093"
    assert params["radius_miles"] == 25.0


def test_search_returns_502_on_inventory_service_error(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [1]
    with patch("src.routers.search.httpx.get", side_effect=httpx.ConnectError("refused")):
        resp = client.get("/v1/search?part_id=1&zip=48093")
    assert resp.status_code == 502
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/test_search.py::test_search_requires_part_id_and_zip -v 2>&1 | head -10
```

Expected: `404` (route not registered).

- [ ] **Step 3: Create `src/routers/search.py`**

Create `gyopart-api/src/routers/search.py`:

```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.config import settings
from src.db import DbDep
from src.models import car_parts
from src.schemas import SearchResponse

router = APIRouter(prefix="/v1", tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search_junkyards(
    db: DbDep,
    part_id: int = Query(...),
    zip: str = Query(..., min_length=5, max_length=5),
    radius_miles: float = Query(50.0, ge=1.0, le=500.0),
):
    car_ids = db.execute(
        select(car_parts.c.car_id).where(car_parts.c.part_id == part_id)
    ).scalars().all()

    if not car_ids:
        return SearchResponse(results=[])

    try:
        resp = httpx.get(
            f"{settings.inventory_api_url}/inventory/search",
            params={
                "car_ids": ",".join(str(i) for i in car_ids),
                "zip": zip,
                "radius_miles": radius_miles,
            },
            timeout=settings.inventory_api_timeout,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"inventory service unavailable: {exc}")

    return SearchResponse(results=resp.json()["results"])
```

- [ ] **Step 4: Register search router and finalize `main.py`**

Replace `gyopart-api/src/main.py` with the complete version:

```python
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import parts, search, vehicles

app = FastAPI(title="Parts Interchange API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(vehicles.router)
app.include_router(parts.router)
app.include_router(search.router)
```

- [ ] **Step 5: Run all gyopart-api tests**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL=postgresql://x:x@localhost/x python -m pytest tests/ -v 2>&1
```

Expected: 20 PASSED (8 vehicles + 6 parts + 5 search + 1 from conftest import).

Actually: 19 PASSED (8 + 6 + 5).

- [ ] **Step 6: Start the server and smoke test**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange" \
INVENTORY_API_URL="http://localhost:8000" \
  uvicorn src.main:app --port 8200 2>&1 &
sleep 3
curl -s http://localhost:8200/v1/vehicles/years | python3 -m json.tool | head -10
```

Expected: JSON array of years.

- [ ] **Step 7: Stop the server**

```bash
pkill -f "uvicorn src.main:app --port 8200" 2>/dev/null; true
```

---

### Task 5: gyopart-ui Scaffold — Vite, Tailwind, Types, API Client

**Files:**
- Create: `gyopart-ui/` (Vite scaffold)
- Create: `gyopart-ui/src/types.ts`
- Create: `gyopart-ui/src/api.ts`
- Create: `gyopart-ui/src/context/AppContext.tsx`

- [ ] **Step 1: Create the Vite project**

```bash
cd /home/daniel/documents/workspace/gyopart
npm create vite@latest gyopart-ui -- --template react-ts
cd gyopart-ui
npm install
```

- [ ] **Step 2: Install Tailwind CSS v4 (Vite plugin)**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-ui
npm install -D tailwindcss @tailwindcss/vite
```

Add the Vite plugin to `vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Replace the content of `src/index.css` with:

```css
@import "tailwindcss";
```

- [ ] **Step 3: Install remaining dependencies**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-ui
npm install axios lucide-react
```

- [ ] **Step 4: Create `src/types.ts`**

Create `gyopart-ui/src/types.ts`:

```typescript
export interface Year { id: number; name: string }
export interface Make { id: number; name: string }
export interface VehicleModel { id: number; name: string; make_id: number }
export interface Trim { id: number; name: string }
export interface Engine { id: number; name: string }
export interface Car {
  id: number
  year_id: number; make_id: number; model_id: number; trim_id: number; engine_id: number
}
export interface Part {
  id: number
  title: string | null
  part_number: string | null
  description: string | null
  other_names: string | null
}
export interface PagedPartsResponse {
  items: Part[]
  total: number
  page: number
  per_page: number
}
export interface VehicleResult {
  vehicle_id: number
  year: number | null
  make: string | null
  model: string | null
  trim: string | null
  row: string | null
  car_id: number | null
}
export interface YardResult {
  location_id: number
  name: string
  address: string | null
  city: string | null
  state: string | null
  zip_code: string | null
  phone: string | null
  distance_miles: number
  matching_vehicles: VehicleResult[]
}
export interface SearchResponse { results: YardResult[] }

export interface SelectedVehicle {
  car: Car
  yearName: string; makeName: string; modelName: string; trimName: string; engineName: string
}
```

- [ ] **Step 5: Create `src/api.ts`**

Create `gyopart-ui/src/api.ts`:

```typescript
import axios from 'axios'
import type {
  Car, Engine, Make, PagedPartsResponse, Part,
  SearchResponse, Trim, VehicleModel, Year,
} from './types'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8200',
})

export const api = {
  years: () =>
    http.get<Year[]>('/v1/vehicles/years').then(r => r.data),

  makes: (year_id: number) =>
    http.get<Make[]>('/v1/vehicles/makes', { params: { year_id } }).then(r => r.data),

  models: (year_id: number, make_id: number) =>
    http.get<VehicleModel[]>('/v1/vehicles/models', { params: { year_id, make_id } }).then(r => r.data),

  trims: (year_id: number, make_id: number, model_id: number) =>
    http.get<Trim[]>('/v1/vehicles/trims', { params: { year_id, make_id, model_id } }).then(r => r.data),

  engines: (year_id: number, make_id: number, model_id: number, trim_id: number) =>
    http.get<Engine[]>('/v1/vehicles/engines', { params: { year_id, make_id, model_id, trim_id } }).then(r => r.data),

  cars: (year_id: number, make_id: number, model_id: number, trim_id: number, engine_id: number) =>
    http.get<Car[]>('/v1/vehicles/cars', { params: { year_id, make_id, model_id, trim_id, engine_id } }).then(r => r.data),

  parts: (car_id: number, filter?: string, page = 1) =>
    http.get<PagedPartsResponse>('/v1/parts', { params: { car_id, filter, page } }).then(r => r.data),

  part: (part_id: number) =>
    http.get<Part>(`/v1/parts/${part_id}`).then(r => r.data),

  search: (part_id: number, zip: string, radius_miles = 50) =>
    http.get<SearchResponse>('/v1/search', { params: { part_id, zip, radius_miles } }).then(r => r.data),
}
```

- [ ] **Step 6: Create `src/context/AppContext.tsx`**

Create `gyopart-ui/src/context/AppContext.tsx`:

```tsx
import { createContext, useContext, useReducer, type ReactNode } from 'react'
import type { Part, SelectedVehicle, YardResult } from '../types'

interface AppState {
  selectedVehicle: SelectedVehicle | null
  activePart: Part | null
  zip: string
  radiusMiles: number
  results: YardResult[]
  searching: boolean
}

type Action =
  | { type: 'SET_VEHICLE'; payload: SelectedVehicle }
  | { type: 'CLEAR_VEHICLE' }
  | { type: 'SET_PART'; payload: Part }
  | { type: 'CLEAR_PART' }
  | { type: 'SET_ZIP'; payload: string }
  | { type: 'SET_RADIUS'; payload: number }
  | { type: 'SET_RESULTS'; payload: YardResult[] }
  | { type: 'SET_SEARCHING'; payload: boolean }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_VEHICLE':
      return { ...state, selectedVehicle: action.payload, activePart: null, results: [] }
    case 'CLEAR_VEHICLE':
      return { ...state, selectedVehicle: null, activePart: null, results: [] }
    case 'SET_PART':
      return { ...state, activePart: action.payload, results: [] }
    case 'CLEAR_PART':
      return { ...state, activePart: null, results: [] }
    case 'SET_ZIP':
      return { ...state, zip: action.payload }
    case 'SET_RADIUS':
      return { ...state, radiusMiles: action.payload }
    case 'SET_RESULTS':
      return { ...state, results: action.payload }
    case 'SET_SEARCHING':
      return { ...state, searching: action.payload }
  }
}

const initial: AppState = {
  selectedVehicle: null,
  activePart: null,
  zip: '',
  radiusMiles: 50,
  results: [],
  searching: false,
}

const AppContext = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial)
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
```

- [ ] **Step 7: Update `src/main.tsx` to wrap with AppProvider**

Replace `gyopart-ui/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppProvider } from './context/AppContext'
import App from './App.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
)
```

- [ ] **Step 8: Verify the dev server starts**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-ui
npm run dev 2>&1 &
sleep 4
curl -s http://localhost:5173 | grep -i "vite\|root" | head -3
pkill -f "vite" 2>/dev/null; true
```

Expected: HTML containing the Vite app root element.

---

### Task 6: gyopart-ui Vehicle Picker + Parts List

**Files:**
- Create: `gyopart-ui/src/hooks/useVehicleTree.ts`
- Create: `gyopart-ui/src/components/TopBar.tsx`
- Create: `gyopart-ui/src/components/VehiclePicker.tsx`
- Create: `gyopart-ui/src/components/PartsList.tsx`
- Modify: `gyopart-ui/src/App.tsx`

- [ ] **Step 1: Create `src/hooks/useVehicleTree.ts`**

Create `gyopart-ui/src/hooks/useVehicleTree.ts`:

```typescript
import { useState, useEffect } from 'react'
import { api } from '../api'
import type { Engine, Make, Trim, VehicleModel, Year } from '../types'

interface Sel {
  year: Year | null
  make: Make | null
  model: VehicleModel | null
  trim: Trim | null
  engine: Engine | null
}

export function useVehicleTree() {
  const [years, setYears] = useState<Year[]>([])
  const [makes, setMakes] = useState<Make[]>([])
  const [models, setModels] = useState<VehicleModel[]>([])
  const [trims, setTrims] = useState<Trim[]>([])
  const [engines, setEngines] = useState<Engine[]>([])
  const [sel, setSel] = useState<Sel>({ year: null, make: null, model: null, trim: null, engine: null })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.years().then(setYears).catch(() => setError('Failed to load years'))
  }, [])

  function selectYear(year: Year) {
    setSel({ year, make: null, model: null, trim: null, engine: null })
    setMakes([]); setModels([]); setTrims([]); setEngines([])
    api.makes(year.id).then(setMakes).catch(() => setError('Failed to load makes'))
  }

  function selectMake(make: Make) {
    if (!sel.year) return
    setSel(s => ({ ...s, make, model: null, trim: null, engine: null }))
    setModels([]); setTrims([]); setEngines([])
    api.models(sel.year.id, make.id).then(setModels).catch(() => setError('Failed to load models'))
  }

  function selectModel(model: VehicleModel) {
    if (!sel.year || !sel.make) return
    setSel(s => ({ ...s, model, trim: null, engine: null }))
    setTrims([]); setEngines([])
    api.trims(sel.year.id, sel.make.id, model.id).then(setTrims).catch(() => setError('Failed to load trims'))
  }

  function selectTrim(trim: Trim) {
    if (!sel.year || !sel.make || !sel.model) return
    setSel(s => ({ ...s, trim, engine: null }))
    setEngines([])
    api.engines(sel.year.id, sel.make.id, sel.model.id, trim.id)
      .then(setEngines).catch(() => setError('Failed to load engines'))
  }

  function selectEngine(engine: Engine) {
    setSel(s => ({ ...s, engine }))
  }

  return { years, makes, models, trims, engines, sel, error, selectYear, selectMake, selectModel, selectTrim, selectEngine }
}
```

- [ ] **Step 2: Create `src/components/TopBar.tsx`**

Create `gyopart-ui/src/components/TopBar.tsx`:

```tsx
export function TopBar() {
  return (
    <header className="fixed top-0 left-0 right-0 h-14 bg-slate-900 border-b border-slate-700 flex items-center px-6 z-10">
      <h1 className="text-white font-bold text-lg tracking-tight">Parts Interchange</h1>
    </header>
  )
}
```

- [ ] **Step 3: Create `src/components/VehiclePicker.tsx`**

Create `gyopart-ui/src/components/VehiclePicker.tsx`:

```tsx
import { useVehicleTree } from '../hooks/useVehicleTree'
import { useApp } from '../context/AppContext'
import { api } from '../api'
import type { Engine, Make, Trim, VehicleModel, Year } from '../types'

const SELECT_CLS = 'w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm disabled:opacity-40'

export function VehiclePicker() {
  const tree = useVehicleTree()
  const { dispatch } = useApp()

  async function handleSetActive() {
    const { year, make, model, trim, engine } = tree.sel
    if (!year || !make || !model || !trim || !engine) return
    const cars = await api.cars(year.id, make.id, model.id, trim.id, engine.id)
    if (!cars.length) return
    dispatch({
      type: 'SET_VEHICLE',
      payload: {
        car: cars[0],
        yearName: year.name,
        makeName: make.name,
        modelName: model.name,
        trimName: trim.name,
        engineName: engine.name,
      },
    })
  }

  const resolved = !!(tree.sel.year && tree.sel.make && tree.sel.model && tree.sel.trim && tree.sel.engine)

  return (
    <div className="flex flex-col gap-3 p-4">
      {tree.error && <p className="text-xs text-red-400">{tree.error}</p>}

      <select className={SELECT_CLS} defaultValue="" onChange={e => {
        const y = tree.years.find((y: Year) => y.id === Number(e.target.value))
        if (y) tree.selectYear(y)
      }}>
        <option value="" disabled>Year</option>
        {tree.years.map((y: Year) => <option key={y.id} value={y.id}>{y.name}</option>)}
      </select>

      <select className={SELECT_CLS} disabled={!tree.sel.year} defaultValue="" onChange={e => {
        const m = tree.makes.find((m: Make) => m.id === Number(e.target.value))
        if (m) tree.selectMake(m)
      }}>
        <option value="" disabled>Make</option>
        {tree.makes.map((m: Make) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>

      <select className={SELECT_CLS} disabled={!tree.sel.make} defaultValue="" onChange={e => {
        const m = tree.models.find((m: VehicleModel) => m.id === Number(e.target.value))
        if (m) tree.selectModel(m)
      }}>
        <option value="" disabled>Model</option>
        {tree.models.map((m: VehicleModel) => <option key={m.id} value={m.id}>{m.name}</option>)}
      </select>

      <select className={SELECT_CLS} disabled={!tree.sel.model} defaultValue="" onChange={e => {
        const t = tree.trims.find((t: Trim) => t.id === Number(e.target.value))
        if (t) tree.selectTrim(t)
      }}>
        <option value="" disabled>Trim</option>
        {tree.trims.map((t: Trim) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>

      <select className={SELECT_CLS} disabled={!tree.sel.trim} defaultValue="" onChange={e => {
        const eng = tree.engines.find((eng: Engine) => eng.id === Number(e.target.value))
        if (eng) tree.selectEngine(eng)
      }}>
        <option value="" disabled>Engine</option>
        {tree.engines.map((eng: Engine) => <option key={eng.id} value={eng.id}>{eng.name}</option>)}
      </select>

      <button
        disabled={!resolved}
        onClick={handleSetActive}
        className="w-full bg-amber-500 text-black font-semibold py-2 rounded text-sm disabled:opacity-40 hover:bg-amber-400 transition-colors"
      >
        Set Active Vehicle
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Create `src/components/PartsList.tsx`**

Create `gyopart-ui/src/components/PartsList.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../context/AppContext'
import type { Part } from '../types'

export function PartsList({ carId }: { carId: number }) {
  const { state, dispatch } = useApp()
  const [parts, setParts] = useState<Part[]>([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.parts(carId, filter || undefined)
      .then(r => setParts(r.items))
      .finally(() => setLoading(false))
  }, [carId, filter])

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="px-4 pt-3 pb-2">
        <input
          className="w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm placeholder-slate-500"
          placeholder="Filter parts..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      </div>
      {loading && <p className="px-4 text-slate-400 text-sm">Loading...</p>}
      <div className="flex-1 overflow-y-auto px-2">
        {parts.map(p => (
          <button
            key={p.id}
            onClick={() => dispatch({ type: 'SET_PART', payload: p })}
            className={`w-full text-left px-3 py-2 rounded mb-0.5 text-sm transition-colors ${
              state.activePart?.id === p.id
                ? 'bg-amber-500/20 text-amber-300'
                : 'hover:bg-slate-700 text-slate-200'
            }`}
          >
            <span className="block font-medium">{p.title ?? 'Unnamed Part'}</span>
            {p.part_number && <span className="text-slate-500 text-xs">#{p.part_number}</span>}
          </button>
        ))}
        {!loading && parts.length === 0 && (
          <p className="px-3 py-2 text-slate-500 text-sm">No parts found.</p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Create minimal `src/App.tsx`**

Replace `gyopart-ui/src/App.tsx`:

```tsx
import { useApp } from './context/AppContext'
import { TopBar } from './components/TopBar'
import { VehiclePicker } from './components/VehiclePicker'
import { PartsList } from './components/PartsList'

export default function App() {
  const { state, dispatch } = useApp()

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="flex flex-1 overflow-hidden pt-14">
        <aside className="w-72 flex-shrink-0 bg-slate-900 flex flex-col border-r border-slate-700 overflow-hidden">
          {!state.selectedVehicle ? (
            <VehiclePicker />
          ) : (
            <>
              <div className="flex items-start justify-between px-4 py-3 border-b border-slate-700 flex-shrink-0">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {state.selectedVehicle.yearName} {state.selectedVehicle.makeName} {state.selectedVehicle.modelName}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {state.selectedVehicle.trimName} · {state.selectedVehicle.engineName}
                  </p>
                </div>
                <button
                  onClick={() => dispatch({ type: 'CLEAR_VEHICLE' })}
                  className="text-xs text-amber-500 hover:underline ml-2 flex-shrink-0"
                >
                  Change
                </button>
              </div>
              <PartsList carId={state.selectedVehicle.car.id} />
            </>
          )}
        </aside>
        <main className="flex-1 overflow-hidden bg-slate-950 flex items-center justify-center text-slate-500">
          <p>Select a part to search nearby junkyards</p>
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Start the dev server and manually verify the vehicle picker**

```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-ui
VITE_API_BASE_URL=http://localhost:8200 npm run dev
```

Start gyopart-api first:
```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange" \
INVENTORY_API_URL="http://localhost:8000" \
  uvicorn src.main:app --port 8200
```

Open http://localhost:5173 in a browser. Verify:
- Year dropdown populates
- Selecting a year loads makes
- Selecting make → model → trim → engine works
- "Set Active Vehicle" shows the vehicle summary in the left rail
- Parts list populates and filter works
- Clicking a part highlights it

---

### Task 7: gyopart-ui Junkyard Search Results + Full Integration

**Files:**
- Create: `gyopart-ui/src/components/ZipInput.tsx`
- Create: `gyopart-ui/src/components/YardCard.tsx`
- Create: `gyopart-ui/src/components/JunkyardResults.tsx`
- Modify: `gyopart-ui/src/App.tsx` (wire in right panel)

- [ ] **Step 1: Create `src/components/ZipInput.tsx`**

Create `gyopart-ui/src/components/ZipInput.tsx`:

```tsx
import { useState } from 'react'
import { Search } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { api } from '../api'

export function ZipInput({ partId }: { partId: number }) {
  const { state, dispatch } = useApp()
  const [zip, setZip] = useState(state.zip)
  const [radius, setRadius] = useState(state.radiusMiles)

  async function handleSearch() {
    if (zip.length !== 5) return
    dispatch({ type: 'SET_SEARCHING', payload: true })
    dispatch({ type: 'SET_ZIP', payload: zip })
    dispatch({ type: 'SET_RADIUS', payload: radius })
    try {
      const data = await api.search(partId, zip, radius)
      dispatch({ type: 'SET_RESULTS', payload: data.results })
    } catch {
      dispatch({ type: 'SET_RESULTS', payload: [] })
    } finally {
      dispatch({ type: 'SET_SEARCHING', payload: false })
    }
  }

  return (
    <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700 flex-shrink-0">
      <input
        className="bg-slate-800 border border-slate-700 text-white rounded px-3 py-2 text-sm w-28 placeholder-slate-500"
        placeholder="ZIP code"
        maxLength={5}
        value={zip}
        onChange={e => setZip(e.target.value.replace(/\D/g, ''))}
        onKeyDown={e => e.key === 'Enter' && handleSearch()}
      />
      <select
        className="bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm"
        value={radius}
        onChange={e => setRadius(Number(e.target.value))}
      >
        {[25, 50, 100, 200].map(r => (
          <option key={r} value={r}>{r} mi</option>
        ))}
      </select>
      <button
        disabled={zip.length !== 5 || state.searching}
        onClick={handleSearch}
        className="flex items-center gap-1.5 bg-amber-500 text-black font-semibold px-4 py-2 rounded text-sm disabled:opacity-40 hover:bg-amber-400 transition-colors"
      >
        <Search size={14} />
        {state.searching ? 'Searching...' : 'Search'}
      </button>
      {state.activePart && (
        <span className="text-slate-400 text-xs ml-1 truncate max-w-36">
          {state.activePart.title ?? 'Part'}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create `src/components/YardCard.tsx`**

Create `gyopart-ui/src/components/YardCard.tsx`:

```tsx
import { MapPin, Phone } from 'lucide-react'
import type { YardResult } from '../types'

export function YardCard({ yard }: { yard: YardResult }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 mb-3 border border-slate-700">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-semibold text-sm">{yard.name}</h3>
          {yard.address && (
            <p className="flex items-center gap-1 text-slate-400 text-xs mt-0.5">
              <MapPin size={10} />
              {yard.address}, {yard.city}, {yard.state} {yard.zip_code}
            </p>
          )}
          {yard.phone && (
            <p className="flex items-center gap-1 text-slate-500 text-xs mt-0.5">
              <Phone size={10} />
              {yard.phone}
            </p>
          )}
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <span className="text-amber-400 font-bold text-lg">{yard.distance_miles.toFixed(1)}</span>
          <span className="text-amber-400 text-xs"> mi</span>
          <p className="text-slate-400 text-xs mt-0.5">
            {yard.matching_vehicles.length} vehicle{yard.matching_vehicles.length !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-700">
            <th className="text-left py-1 font-medium">Year</th>
            <th className="text-left py-1 font-medium">Make</th>
            <th className="text-left py-1 font-medium">Model</th>
            <th className="text-left py-1 font-medium">Trim</th>
            <th className="text-left py-1 font-medium">Row</th>
          </tr>
        </thead>
        <tbody>
          {yard.matching_vehicles.map(v => (
            <tr key={v.vehicle_id} className="text-slate-300 border-b border-slate-700/40 last:border-0">
              <td className="py-1">{v.year ?? '—'}</td>
              <td className="py-1">{v.make ?? '—'}</td>
              <td className="py-1">{v.model ?? '—'}</td>
              <td className="py-1">{v.trim ?? '—'}</td>
              <td className="py-1 font-mono">{v.row ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 3: Create `src/components/JunkyardResults.tsx`**

Create `gyopart-ui/src/components/JunkyardResults.tsx`:

```tsx
import { useApp } from '../context/AppContext'
import { ZipInput } from './ZipInput'
import { YardCard } from './YardCard'

export function JunkyardResults() {
  const { state } = useApp()

  if (!state.activePart) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 text-sm">Select a part to search nearby junkyards</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <ZipInput partId={state.activePart.id} />
      <div className="flex-1 overflow-y-auto p-4">
        {state.searching && (
          <p className="text-slate-400 text-sm">Searching...</p>
        )}
        {!state.searching && state.zip && state.results.length === 0 && (
          <p className="text-slate-500 text-sm">
            No yards found within {state.radiusMiles} miles of {state.zip}.
          </p>
        )}
        {state.results.map(yard => (
          <YardCard key={yard.location_id} yard={yard} />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Update `src/App.tsx` to wire in the right panel**

Replace `gyopart-ui/src/App.tsx` with the complete version:

```tsx
import { useApp } from './context/AppContext'
import { TopBar } from './components/TopBar'
import { VehiclePicker } from './components/VehiclePicker'
import { PartsList } from './components/PartsList'
import { JunkyardResults } from './components/JunkyardResults'

export default function App() {
  const { state, dispatch } = useApp()

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="flex flex-1 overflow-hidden pt-14">
        {/* Left rail */}
        <aside className="w-72 flex-shrink-0 bg-slate-900 flex flex-col border-r border-slate-700 overflow-hidden">
          {!state.selectedVehicle ? (
            <VehiclePicker />
          ) : (
            <>
              <div className="flex items-start justify-between px-4 py-3 border-b border-slate-700 flex-shrink-0">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {state.selectedVehicle.yearName} {state.selectedVehicle.makeName}{' '}
                    {state.selectedVehicle.modelName}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {state.selectedVehicle.trimName} · {state.selectedVehicle.engineName}
                  </p>
                </div>
                <button
                  onClick={() => dispatch({ type: 'CLEAR_VEHICLE' })}
                  className="text-xs text-amber-500 hover:underline ml-2 flex-shrink-0"
                >
                  Change
                </button>
              </div>
              <PartsList carId={state.selectedVehicle.car.id} />
            </>
          )}
        </aside>

        {/* Right panel */}
        <main className="flex-1 overflow-hidden bg-slate-950 flex flex-col">
          <JunkyardResults />
        </main>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Start gyopart-api and gyopart-ui, verify the full flow**

Terminal 1 — gyopart-api:
```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-api
PARTS_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange" \
INVENTORY_API_URL="http://localhost:8000" \
  uvicorn src.main:app --port 8200
```

Terminal 2 — gyopart-ui:
```bash
cd /home/daniel/documents/workspace/gyopart/gyopart-ui
VITE_API_BASE_URL=http://localhost:8200 npm run dev
```

Open http://localhost:5173. Walk the full flow:
1. Pick year → make → model → trim → engine → "Set Active Vehicle"
2. Parts list appears in left rail; filter works
3. Click a part — it highlights and the right panel shows zip input
4. Enter a 5-digit zip (e.g. `48093`) and click Search
5. Yard cards appear with distance and matching vehicle rows
6. "Change" button in left rail resets to vehicle picker

---

## Self-Review

**Spec coverage:**
- [x] Vehicle picker (year/make/model/trim/engine) — Tasks 2 and 6
- [x] Parts search for a car, paginated, filterable — Tasks 3 and 6
- [x] Compatible car ID resolution — Task 3 (`/v1/parts/{id}/compatible-cars`)
- [x] Junkyard search: part → car_ids → inventory API → ranked yards — Tasks 4 and 7
- [x] Zip code input (not lat/lng) for search — Task 7 `ZipInput`
- [x] Adjustable radius (25/50/100/200 mi) — Task 7 `ZipInput`
- [x] Yard results with per-vehicle detail (year/make/model/trim/row) — Task 7 `YardCard`
- [x] CORS configured for localhost dev — Task 4 `main.py`
- [x] 502 passthrough when inventory service is down — Task 4 search route
- [x] No git commits — noted throughout

**Placeholder scan:** No TBDs. All code blocks are complete and self-contained.

**Type consistency:**
- `SelectedVehicle` defined in `types.ts`, used in `AppContext.tsx`, `VehiclePicker.tsx`, `App.tsx`
- `useVehicleTree` returns `{ selectYear, selectMake, selectModel, selectTrim, selectEngine }` — all used in `VehiclePicker`
- `api.search(partId, zip, radiusMiles)` → `SearchResponse` — used in `ZipInput`
- `YardResult.matching_vehicles` → `VehicleResult[]` — rendered in `YardCard`
- `dispatch({ type: 'SET_PART', payload: p })` — action handled in reducer, `state.activePart.id` used in `JunkyardResults`
