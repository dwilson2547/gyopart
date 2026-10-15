from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from pipeline.car_matcher import (
    DECODE_FAILED, MAKE_NOT_IN_CATALOGUE, MODEL_NOT_IN_CATALOGUE, MODEL_YEAR_GAP, YEAR_NOT_IN_CATALOGUE,
    Mapping, applicable_mappings, decoded_model_keys, name_key, decoded_engine, decoded_vehicle_fields,
    match_decoded, parse_catalogue_engine,
)
from pipeline.pi_schema import (
    pi_car_table, pi_engine_table, pi_make_table, pi_metadata, pi_model_table, pi_trim_table, pi_year_table,
)

# 2010 Chrysler Sebring as NHTSA decodes it (US Auto Supply feed, 2026-10-12)
SEBRING = {"VIN": "1C3CC4FBXAN197479", "Make": "CHRYSLER", "Model": "Sebring", "ModelYear": "2010", "Trim": "LX",
           "DisplacementL": "2.4", "EngineCylinders": "4", "FuelTypePrimary": "Gasoline",
           "DriveType": "FWD/Front-Wheel Drive", "BodyClass": "Sedan/Saloon", "Doors": "4", "Turbo": "No"}


def _catalogue(cars):
    """A real (SQLite) catalogue from (car id, year, make, model, trim, engine) tuples."""
    # One shared connection: an in-memory SQLite DB is per connection, and API tests use other threads.
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    pi_metadata.create_all(engine)
    ids: dict[tuple, int] = {}

    def id_of(table, name, **extra):
        k = (table.name, name, *extra.values())
        if k not in ids:
            ids[k] = len(ids) + 1
            conn.execute(insert(table).values(id=ids[k], name=name, **extra))
        return ids[k]

    with engine.begin() as conn:
        for car_id, year, make, model, trim, eng in cars:
            make_id = id_of(pi_make_table, make)
            conn.execute(insert(pi_car_table).values(
                id=car_id, year_id=id_of(pi_year_table, year), make_id=make_id,
                model_id=id_of(pi_model_table, model, make_id=make_id),
                trim_id=id_of(pi_trim_table, trim) if trim else None,
                engine_id=id_of(pi_engine_table, eng) if eng else None))
    return engine


def _pi_engine(rows, model="Sebring", year="2010", make="Chrysler"):
    """(id, trim, engine[, model]) rows, all of one year and make."""
    return _catalogue([(r[0], year, make, r[3] if len(r) > 3 else model, r[1], r[2]) for r in rows])


def test_parse_catalogue_engine():
    assert parse_catalogue_engine("2.4L L4 - Gas").__dict__ == {"displacement_l": 2.4, "cylinders": 4, "fuel": "gas"}
    assert parse_catalogue_engine("2.7L V6 - Flex").fuel == "flex"
    assert parse_catalogue_engine("3.5L V6 - Electric/Gas").fuel == "hybrid"
    assert parse_catalogue_engine("1.8L L4 - FULL HYBRID EV-GAS (FHEV)").fuel == "hybrid"
    assert parse_catalogue_engine("6.7L V8 - Diesel").fuel == "diesel"
    assert parse_catalogue_engine("weird").displacement_l is None


def test_decoded_engine_flex_from_secondary_fuel():
    raw = dict(SEBRING, DisplacementL="2.7", EngineCylinders="6", FuelTypeSecondary="Ethanol (E85)")
    assert decoded_engine(raw).__dict__ == {"displacement_l": 2.7, "cylinders": 6, "fuel": "flex"}


def test_match_narrows_by_engine_fuel_and_trim_to_exact():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas"), (3, "Touring", "2.7L V6 - Gas"),
            (4, "Touring", "2.7L V6 - Flex"), (5, "Limited", "3.5L V6 - Gas")]
    m = match_decoded(SEBRING, _pi_engine(rows))
    assert m.candidates == [1]
    assert m.exact
    assert m.narrowed_by == ["engine", "trim"]


def test_match_keeps_candidates_when_trim_unknown():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas"), (3, "Touring", "2.7L V6 - Gas")]
    m = match_decoded(dict(SEBRING, Trim=""), _pi_engine(rows))
    assert m.candidates == [1, 2]
    assert not m.exact


def test_match_ignores_a_filter_that_would_empty_the_set():
    rows = [(1, "LX", "2.4L L4 - Gas"), (2, "Touring", "2.4L L4 - Gas")]
    m = match_decoded(dict(SEBRING, Trim="Sport"), _pi_engine(rows))
    assert m.candidates == [1, 2]


def test_match_empty_when_ymm_not_in_catalogue():
    assert match_decoded(SEBRING, _pi_engine([])).candidates == []
    assert match_decoded(dict(SEBRING, Model=""), _pi_engine([(1, "LX", "2.4L L4 - Gas")])).candidates == []


def test_decoded_vehicle_fields():
    assert decoded_vehicle_fields(SEBRING) == {
        "engine_size": 2.4, "engine_cylinders": 4, "fuel_type": "G", "engine_aspiration": "N/A",
        "drive_type": "FWD", "body_type": "Sedan/Saloon", "doors": 4, "trim": "LX",
    }


def test_name_keys_are_loose():
    assert name_key("Town and Country") == name_key("Town & Country")
    assert name_key("F-150") == name_key("F150")
    assert decoded_model_keys({"Model": "Caravan/Grand Caravan"}) == {"caravangrandcaravan", "caravan", "grandcaravan"}
    assert name_key("Ram 1500") in decoded_model_keys({"Model": "Ram", "Series": "1500"})


def test_match_picks_the_model_among_the_makes_cars():
    rows = [(1, "LX", "3.3L V6 - Gas", "Town & Country"), (2, "LX", "2.4L L4 - Gas", "Sebring")]
    raw = dict(SEBRING, Model="Town and Country", DisplacementL="3.3", EngineCylinders="6", Trim="")
    assert match_decoded(raw, _pi_engine(rows)).candidates == [1]


# ── why a decode didn't match (admin-rewrite-design §2.1) ─────────────────────────────────────────

MIXED = [(1, "2010", "Chrysler", "Sebring", "LX", "2.4L L4 - Gas"),
         (2, "2008", "Chrysler", "PT Cruiser", "Base", "2.4L L4 - Gas"),
         (3, "2010", "Chevrolet", "Prizm", "Base", "1.8L L4 - Gas"),
         (4, "2004", "Mercedes-Benz", "C230", "Base", "1.8L L4 - Gas")]


def test_reason_decode_failed_without_year_make_model():
    m = match_decoded(dict(SEBRING, Model=""), _catalogue(MIXED))
    assert (m.candidates, m.reason) == ([], DECODE_FAILED)


def test_reason_make_not_in_catalogue():
    m = match_decoded(dict(SEBRING, Make="SAAB", Model="9-3"), _catalogue(MIXED))
    assert m.reason == MAKE_NOT_IN_CATALOGUE


def test_reason_year_not_in_catalogue_for_the_make():
    m = match_decoded(dict(SEBRING, ModelYear="2015"), _catalogue(MIXED))
    assert m.reason == YEAR_NOT_IN_CATALOGUE


def test_reason_model_year_gap_when_the_model_exists_in_other_years():
    m = match_decoded(dict(SEBRING, Model="PT Cruiser"), _catalogue(MIXED))
    assert m.reason == MODEL_YEAR_GAP


def test_reason_model_not_in_catalogue():
    m = match_decoded(dict(SEBRING, Model="Crossfire"), _catalogue(MIXED))
    assert m.reason == MODEL_NOT_IN_CATALOGUE


def test_a_match_has_no_reason():
    m = match_decoded(SEBRING, _catalogue(MIXED))
    assert (m.candidates, m.reason, m.mapped) == ([1], None, False)


# ── decode mappings (admin-rewrite-design §2.2) ───────────────────────────────────────────────────

def _mapping(make, model, cat_make, cat_model, series=None, year_from=None, year_to=None):
    return Mapping(name_key(make), name_key(model), name_key(series) if series else None,
                   year_from, year_to, cat_make, cat_model)


def test_mapping_supplies_the_catalogue_model_name():
    benz = {"Make": "MERCEDES-BENZ", "Model": "C-Class", "ModelYear": "2004", "DisplacementL": "1.8",
            "EngineCylinders": "4"}
    cat = _catalogue(MIXED)
    assert match_decoded(benz, cat).reason == MODEL_NOT_IN_CATALOGUE
    m = match_decoded(benz, cat, [_mapping("Mercedes-Benz", "C-Class", "Mercedes-Benz", "C230")])
    assert (m.candidates, m.mapped) == ([4], True)


def test_cross_make_mapping():
    geo = {"Make": "GEO", "Model": "Prizm", "ModelYear": "2010"}
    cat = _catalogue(MIXED)
    assert match_decoded(geo, cat).reason == MAKE_NOT_IN_CATALOGUE
    assert match_decoded(geo, cat, [_mapping("Geo", "Prizm", "Chevrolet", "Prizm")]).candidates == [3]


def test_mapping_respects_series_and_year_range():
    raw = {"Make": "CHEVROLET", "Model": "Silverado", "Series": "1500 (1/2 Ton)", "ModelYear": "2004"}
    assert applicable_mappings(raw, [_mapping("Chevrolet", "Silverado", "Chevrolet", "Silverado 1500",
                                              series="1500 (1/2 Ton)")])
    assert not applicable_mappings(raw, [_mapping("Chevrolet", "Silverado", "Chevrolet", "Silverado 2500",
                                                  series="2500 (3/4 Ton)")])
    assert applicable_mappings(raw, [_mapping("Chevrolet", "Silverado", "Chevrolet", "Silverado 1500")])
    assert not applicable_mappings(raw, [_mapping("Chevrolet", "Silverado", "Chevrolet", "Silverado 1500",
                                                  year_from=2007)])
    assert not applicable_mappings(raw, [_mapping("Chevrolet", "Silverado", "Chevrolet", "Silverado 1500",
                                                  year_to=2003)])
    assert not applicable_mappings(raw, [_mapping("GMC", "Silverado", "Chevrolet", "Silverado 1500")])
