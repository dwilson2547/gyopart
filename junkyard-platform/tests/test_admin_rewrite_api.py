"""Admin rewrite phase 2 API (admin_api/api): the parts that don't need Postgres — suggestion ranking, the
preview simulation over a real (SQLite) catalogue, request validation and the DB-down error mapping.
Group listing uses Postgres-only SQL (regexp_replace, array_agg) and was verified against the dev DB."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from admin_api.api.catalogue import similarity, suggest
from admin_api.api.fixes import MappingRequest, simulate_mapping
from tests.test_car_matcher import _catalogue

CATALOGUE = [
    (1, "2004", "Mercedes-Benz", "C 230", "Base", "1.8L L4 - Gas"),
    (2, "2004", "Mercedes-Benz", "C 320", "Base", "3.2L V6 - Gas"),
    (3, "2004", "Mercedes-Benz", "CLK 320", "Base", "3.2L V6 - Gas"),
    (4, "2004", "Mercedes-Benz", "E 320", "Base", "3.2L V6 - Gas"),
    (5, "2005", "Dodge", "Ram 1500", "ST", "4.7L V8 - Gas"),
    (6, "2005", "Dodge", "Ram 2500", "ST", "5.7L V8 - Gas"),
]


def test_class_names_suggest_their_variants():
    assert similarity("C-Class", "C 230") >= 0.85
    assert similarity("C-Class", "E 320") < 0.5
    assert similarity("Silverado HD 2500", "Silverado 2500 HD") > 0.8


def test_suggest_ranks_in_range_models_by_similarity():
    names = [m["name"] for m in suggest(_catalogue(CATALOGUE), "Mercedes-Benz", ["C-Class"], 2000, 2010)]
    assert names[:2] == ["C 230", "C 320"] and "E 320" not in names


def test_cross_make_suggestion():
    names = [m["name"] for m in suggest(_catalogue(CATALOGUE), "Dodge", ["1500", "Ram 1500"], 2001, 2009)]
    assert names[0] == "Ram 1500"


def test_preview_simulation_counts_matches_and_exact():
    benz = {"Make": "MERCEDES-BENZ", "Model": "C-Class", "ModelYear": "2004"}
    raws = [dict(benz, DisplacementL="1.8", EngineCylinders="4"), dict(benz, DisplacementL="3.2", EngineCylinders="6"),
            dict(benz), dict(benz, ModelYear="2015")]
    req = MappingRequest(make="MERCEDES-BENZ", model="C-Class",
                         targets=[{"make": "Mercedes-Benz", "model": "C 230"}, {"make": "Mercedes-Benz", "model": "C 320"}])
    r = simulate_mapping(_catalogue(CATALOGUE), raws, req.mappings())
    assert (r["vehicles"], r["wouldMatch"], r["exact"]) == (4, 3, 2)   # the bare decode can be either
    assert r["unmatched"] == {"year_not_in_catalogue": 1}


def test_mapping_request_validation():
    with pytest.raises(ValidationError):
        MappingRequest(make="X", model="Y", targets=[])
    with pytest.raises(ValidationError):
        MappingRequest(make="X", model="Y", year_from=2010, year_to=2001, targets=[{"make": "A", "model": "B"}])


def test_unknown_target_is_a_field_error():
    import admin_api.main as m
    with patch.object(m, "_engine", MagicMock()), patch.object(m, "_pi_engine", _catalogue(CATALOGUE)):
        r = TestClient(m.app).post("/api/mappings/preview", json={
            "make": "MERCEDES-BENZ", "model": "C-Class", "targets": [{"make": "Mercedes-Benz", "model": "C 999"}]})
    assert r.status_code == 422 and r.json()["detail"]["field"] == "targets.0"


def test_database_down_is_a_503():
    import admin_api.main as m
    down = OperationalError("select 1", {}, Exception("connection refused"))
    with patch.object(m, "_engine", MagicMock()), patch.object(m, "_pi_engine", MagicMock()), \
         patch("admin_api.api.discrepancies.summary", side_effect=down):
        r = TestClient(m.app).get("/api/discrepancies/summary")
    assert r.status_code == 503
