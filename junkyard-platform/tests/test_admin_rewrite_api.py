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


# ── phase 3: vehicles ──────────────────────────────────────────────────────────────────────────────

def test_scrapejob_found_by_label_then_by_name(monkeypatch):
    from admin_api.api import scrapejobs
    api = MagicMock()
    api.list_namespaced_custom_object.return_value = {"items": []}
    api.get_namespaced_custom_object.return_value = {"metadata": {"name": "pull-a-part", "namespace": "ns"}}
    monkeypatch.setattr(scrapejobs, "_api", lambda: api)
    monkeypatch.setenv("SCRAPEJOB_NAMESPACE", "ns")
    assert scrapejobs.find("pull_a_part")["metadata"]["name"] == "pull-a-part"
    assert api.get_namespaced_custom_object.call_args.args[-1] == "pull-a-part"   # source _ -> -
    api.list_namespaced_custom_object.return_value = {"items": [{"metadata": {"name": "picknpull-sa"}}]}
    assert scrapejobs.find("picknpullsa")["metadata"]["name"] == "picknpull-sa"
    assert "gyopart.danwils.com/source=picknpullsa" in str(api.list_namespaced_custom_object.call_args)


def test_scrapejob_summary_reads_operator_status():
    from admin_api.api.scrapejobs import ANNOTATION_RUN_NOW, summarize
    cr = {"metadata": {"name": "j", "namespace": "ns", "annotations": {ANNOTATION_RUN_NOW: "1"}},
          "spec": {"suspend": True},
          "status": {"phase": "Healthy", "currentRun": {"k8sJob": "j-123"}, "nextRunAt": "2026-10-16T09:00:00Z",
                     "lastRun": {"result": "Succeeded", "items": 812, "finishedAt": "2026-10-15T09:00:00Z"}}}
    s = summarize(cr)
    assert (s["suspended"], s["running"], s["runNowRequested"], s["lastRun"]["items"]) == (True, True, True, 812)
    cr["status"]["handled"] = {"runNow": "1"}      # the operator picked that request up
    assert summarize(cr)["runNowRequested"] is False


def test_manual_match_refuses_a_car_not_in_the_catalogue():
    import admin_api.main as m
    with patch.object(m, "_engine", MagicMock()), patch.object(m, "_pi_engine", _catalogue(CATALOGUE)):
        r = TestClient(m.app).post("/api/vehicles/1/manual", json={"car_id": 999})
    assert r.status_code == 422 and r.json()["detail"]["field"] == "car_id"
