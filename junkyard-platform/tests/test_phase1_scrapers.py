import os

import pytest
from sqlalchemy import text

from junkyard_common.db import get_engine


@pytest.fixture(scope="session")
def engine():
    return get_engine()


def test_db_engine_connects(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_db_engine_default_url_from_env():
    """get_engine() must raise KeyError if JUNKYARD_DATABASE_URL is not set."""
    original = os.environ.pop("JUNKYARD_DATABASE_URL", None)
    try:
        with pytest.raises(KeyError):
            get_engine()
    finally:
        if original is not None:
            os.environ["JUNKYARD_DATABASE_URL"] = original


def test_pic_n_pull_vehicle_has_trim_and_image_directly(engine):
    """trim and preview_image_url must be columns on Vehicle, not VehicleDetail."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("vehicles")}
    assert "trim" in cols
    assert "preview_image_url" in cols
    assert "vehicle_details" not in inspector.get_table_names()


def test_parts_galore_upsert(engine):
    """parts-galore vehicle should upsert with source='parts_galore' and source_key=VIN."""
    import datetime
    from sqlalchemy.orm import Session
    from junkyard_common.models import Location, Vehicle

    SOURCE = "parts_galore"
    VIN = "TESTVIN1234567890"
    now = datetime.datetime.utcnow()

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1", name="Parts Galore",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=VIN,
            year=2005, make="Ford", model="Explorer", vin=VIN,
            arrival_date=datetime.datetime(2024, 1, 15),
            row="C7",
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=VIN).first()
        assert fetched is not None
        assert fetched.make == "Ford"
        assert fetched.row == "C7"
        assert fetched.arrival_date == datetime.datetime(2024, 1, 15)

        db.delete(fetched)
        db.commit()


def test_us_auto_vehicle_extras(engine):
    """us_auto vehicles must store hol_model/reference/vehicle_row/location_string in extras JSONB."""
    import datetime
    from sqlalchemy.orm import Session
    from junkyard_common.models import Location, Vehicle

    SOURCE = "us_auto_supply"
    STOCK = "TEST-STOCK-001"
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1",
                name="US Auto Supply — Sterling Heights",
                city="Sterling Heights", state="MI",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=STOCK,
            year=2010, make="Chevrolet", model="Silverado", vin="1GCNKPEA2BZ123456",
            mileage=120000,
            extras={"hol_model": "C10", "reference": "REF001",
                    "vehicle_row": "A", "location_string": "Sterling Hts",
                    "last_update": "05/01/2026 10:00:00 AM", "status": "0"},
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=STOCK).first()
        assert fetched.extras["hol_model"] == "C10"
        assert fetched.extras["reference"] == "REF001"
        assert fetched.mileage == 120000

        db.delete(fetched)
        db.commit()


def test_ryans_vehicle_extras(engine):
    """ryans vehicles must store inventory_id/name/exterior_color in extras JSONB."""
    import datetime
    from sqlalchemy.orm import Session
    from junkyard_common.models import Location, Vehicle

    SOURCE = "ryans_pic_a_part"
    API_ID = "test-es-id-001"
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="1").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="1",
                name="Ryan's Pick-a-Part — Detroit",
                city="Detroit", state="MI",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=API_ID,
            year=2012, make="Honda", model="Accord",
            preview_image_url="https://cdn.example.com/img.jpg",
            extras={"inventory_id": "INV123", "name": "2012 Honda Accord",
                    "exterior_color": "Silver",
                    "added_date_ms": 1714000000000, "api_modified_ms": 1714500000000},
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=API_ID).first()
        assert fetched.extras["exterior_color"] == "Silver"
        assert fetched.preview_image_url == "https://cdn.example.com/img.jpg"

        db.delete(fetched)
        db.commit()


def test_pull_a_part_source_key_format(engine):
    """PAP vehicles use source_key='{ticket_id}:{line_id}' with extras for PAP-specific IDs."""
    import datetime
    from sqlalchemy.orm import Session
    from junkyard_common.models import Location, Vehicle

    SOURCE = "pull_a_part"
    SOURCE_KEY = "987654:12"
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    with Session(engine) as db:
        loc = db.query(Location).filter_by(source=SOURCE, source_location_id="99").first()
        if loc is None:
            loc = Location(
                source=SOURCE, source_location_id="99",
                name="Pull-A-Part — Test Location",
                chain="Pull-A-Part", city="Atlanta", state="GA",
                is_active=True, first_seen_at=now, last_seen_at=now,
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        v = Vehicle(
            location_id=loc.id, source=SOURCE, source_key=SOURCE_KEY,
            year=2008, make="Toyota", model="Camry", vin="4T1BE46K48U123456",
            row="D3",
            trim="LE", engine_cylinders=4, trans_type="A",
            extras={"vin_id": 111, "make_id": 7, "model_id": 42, "vin_decoded_id": 555},
            detail_fetched_at=now,
            is_active=True, first_seen_at=now, last_seen_at=now,
        )
        db.add(v)
        db.commit()
        db.refresh(v)

        fetched = db.query(Vehicle).filter_by(source=SOURCE, source_key=SOURCE_KEY).first()
        assert fetched.extras["make_id"] == 7
        assert fetched.trim == "LE"
        assert fetched.engine_cylinders == 4
        assert fetched.detail_fetched_at is not None

        db.delete(fetched)
        db.commit()
