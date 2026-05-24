"""Admin API tests — unit (mocked DB) and integration (skip without DB)."""
import pytest
from admin_api.models import (
    DiscrepancyGroup,
    DiscrepancyListResponse,
    RuleResponse,
    CreateRuleRequest,
    ManualOverrideRequest,
    LlmSuggestion,
)


def test_discrepancy_group_fields():
    g = DiscrepancyGroup(
        source="pic_n_pull",
        raw_make="CHEV",
        raw_model="SILVERADO 1500",
        count=47,
        vehicle_ids=[1, 2, 3],
        best_make_match="Chevrolet",
        best_make_score=0.91,
        best_model_match="Silverado 1500",
        best_model_score=0.87,
        candidate_car_id=None,
    )
    assert g.count == 47
    assert g.source == "pic_n_pull"


def test_discrepancy_list_response():
    g = DiscrepancyGroup(
        source="x", raw_make="A", raw_model="B", count=1,
        vehicle_ids=[10], best_make_match=None, best_make_score=None,
        best_model_match=None, best_model_score=None, candidate_car_id=None,
    )
    resp = DiscrepancyListResponse(groups=[g], total=1)
    assert resp.total == 1
    assert len(resp.groups) == 1


def test_create_rule_request_defaults():
    req = CreateRuleRequest(
        field="make",
        rule_type="exact",
        raw_value="CHEV",
        canonical_value="Chevrolet",
    )
    assert req.scope == "global"
    assert req.priority == 100
    assert req.make_context is None
    assert req.source is None
    assert req.location_id is None


def test_manual_override_request():
    req = ManualOverrideRequest(car_id=42)
    assert req.car_id == 42


def test_rule_response_fields():
    import datetime
    r = RuleResponse(
        id=1, scope="global", source=None, location_id=None,
        field="make", rule_type="exact", raw_value="CHEV",
        canonical_value="Chevrolet", make_context=None, priority=100,
        is_active=True, created_by="manual", created_at=datetime.datetime.utcnow(),
        applied_count=5, llm_confidence=None, llm_rationale=None,
        approved_at=None, approved_by=None,
    )
    assert r.id == 1
    assert r.is_active is True


def test_llm_suggestion_fields():
    s = LlmSuggestion(
        rule_id=10,
        field="make",
        rule_type="exact",
        raw_value="CHEV",
        canonical_value="Chevrolet",
        make_context=None,
        llm_confidence=0.95,
        llm_rationale="CHEV is a common abbreviation for Chevrolet",
        source="pic_n_pull",
        affected_count=47,
    )
    assert s.llm_confidence == 0.95


import admin_api.main as _admin_main
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient


def _mock_groups():
    return [
        {
            "source": "pic_n_pull",
            "raw_make": "CHEV",
            "raw_model": "SILVERADO 1500",
            "count": 47,
            "vehicle_ids": [1, 2, 3],
            "best_make_match": "Chevrolet",
            "best_make_score": 0.91,
            "best_model_match": "Silverado 1500",
            "best_model_score": 0.87,
            "candidate_car_id": 123,
        }
    ]


def _patched_client(extra_patches=None):
    """Return a context manager that yields a TestClient with engine+key patched."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        patches = [
            patch.object(_admin_main, "_engine", MagicMock()),
            patch.object(_admin_main, "_ADMIN_KEY", "test-key"),
        ]
        if extra_patches:
            patches.extend(extra_patches)
        started = [p.start() for p in patches]
        try:
            yield TestClient(_admin_main.app, headers={"X-Admin-Key": "test-key"})
        finally:
            for p in patches:
                p.stop()

    return _ctx()


def test_list_discrepancies_requires_auth():
    with patch.object(_admin_main, "_engine", MagicMock()), \
         patch.object(_admin_main, "_ADMIN_KEY", "test-key"):
        client = TestClient(_admin_main.app)  # no X-Admin-Key header
        resp = client.get("/admin/discrepancies?status=unresolved")
    assert resp.status_code == 401


def test_list_discrepancies_returns_groups():
    with patch("admin_api.discrepancies.get_grouped_discrepancies", return_value=_mock_groups()):
        with _patched_client() as client:
            resp = client.get("/admin/discrepancies?status=unresolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["groups"][0]["raw_make"] == "CHEV"
    assert data["groups"][0]["count"] == 47


def test_list_discrepancies_invalid_status_returns_422():
    with _patched_client() as client:
        resp = client.get("/admin/discrepancies?status=bad_value")
    assert resp.status_code == 422


def test_ignore_discrepancy_group():
    with patch("admin_api.discrepancies.ignore_group", return_value=12) as mock_ignore:
        with _patched_client() as client:
            resp = client.post(
                "/admin/discrepancies/ignore",
                json={"source": "pic_n_pull", "raw_make": "CHEV", "raw_model": "SILVERADO 1500"},
            )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 12
    mock_ignore.assert_called_once()


import datetime as _dt
import admin_api.main as _admin_main


def _make_rule_row(**kwargs):
    defaults = dict(
        id=1, scope="global", source=None, location_id=None,
        field="make", rule_type="exact", raw_value="CHEV",
        canonical_value="Chevrolet", make_context=None, priority=100,
        is_active=True, created_by="manual",
        created_at=_dt.datetime(2026, 1, 1),
        applied_count=0, llm_confidence=None, llm_rationale=None,
        approved_at=None, approved_by=None,
    )
    defaults.update(kwargs)
    return defaults


def test_list_rules_returns_rules():
    with patch("admin_api.rules.list_rules", return_value=[_make_rule_row()]):
        with _patched_client() as client:
            resp = client.get("/admin/rules")
    assert resp.status_code == 200
    assert len(resp.json()["rules"]) == 1


def test_create_rule_manual():
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row()) as mock_create:
        with _patched_client() as client:
            resp = client.post("/admin/rules", data={
                "field": "make",
                "rule_type": "exact",
                "raw_value": "CHEV",
                "canonical_value": "Chevrolet",
            })
    assert resp.status_code == 200
    mock_create.assert_called_once()
    assert resp.json()["is_active"] is True


def test_create_rule_invalid_field_returns_422():
    with _patched_client() as client:
        resp = client.post("/admin/rules", data={
            "field": "engine",
            "rule_type": "exact",
            "raw_value": "V8",
            "canonical_value": "V8",
        })
    assert resp.status_code == 422


def test_approve_rule_triggers_reprocess():
    with patch("admin_api.rules.approve_rule", return_value=_make_rule_row(approved_by="admin")):
        with patch("admin_api.rules.run_reprocess") as mock_reprocess:
            with _patched_client() as client:
                resp = client.post("/admin/rules/1/approve", json={"approved_by": "admin"})
    assert resp.status_code == 200
    assert resp.json()["approved_by"] == "admin"


def test_deactivate_rule():
    with patch("admin_api.rules.deactivate_rule", return_value=_make_rule_row(is_active=False)):
        with _patched_client() as client:
            resp = client.post("/admin/rules/1/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_manual_override_updates_vehicle():
    with patch("admin_api.rules.apply_manual_override", return_value={"vehicle_id": 42, "car_id": 99}) as mock_override:
        with _patched_client() as client:
            resp = client.patch("/admin/vehicles/42/car-id", json={"car_id": 99})
    assert resp.status_code == 200
    assert resp.json()["car_id"] == 99
    assert mock_override.called


def test_manual_override_invalid_car_id_returns_422():
    with _patched_client() as client:
        resp = client.patch("/admin/vehicles/42/car-id", json={"car_id": 0})
    assert resp.status_code == 422


def test_build_llm_prompt_includes_groups():
    from admin_api.llm_suggester import build_prompt
    groups = [
        {"source": "pic_n_pull", "raw_make": "CHEV", "raw_model": "SILVERADO 1500", "count": 47, "vehicle_ids": [1, 2]},
    ]
    prompt = build_prompt(groups, canonical_makes=["Chevrolet", "GMC", "Ford"])
    assert "CHEV" in prompt
    assert "SILVERADO 1500" in prompt
    assert "Chevrolet" in prompt
    assert "47" in prompt


def test_parse_llm_response_valid():
    from admin_api.llm_suggester import parse_llm_response
    raw = '{"suggestions": [{"group_index": 0, "field": "make", "rule_type": "exact", "raw_value": "CHEV", "canonical_value": "Chevrolet", "make_context": null, "confidence": 0.95, "rationale": "Common abbreviation"}]}'
    groups = [{"source": "pic_n_pull", "raw_make": "CHEV", "raw_model": "SILVERADO 1500", "count": 47, "vehicle_ids": [1, 2]}]
    suggestions = parse_llm_response(raw, groups=groups)
    assert len(suggestions) == 1
    assert suggestions[0]["canonical_value"] == "Chevrolet"
    assert suggestions[0]["source"] == "pic_n_pull"
    assert suggestions[0]["affected_vehicle_ids"] == [1, 2]


def test_parse_llm_response_invalid_json_returns_empty():
    from admin_api.llm_suggester import parse_llm_response
    suggestions = parse_llm_response("not json at all", groups=[])
    assert suggestions == []


def test_parse_llm_response_low_confidence_filtered():
    from admin_api.llm_suggester import parse_llm_response
    raw = '{"suggestions": [{"group_index": 0, "field": "make", "rule_type": "exact", "raw_value": "XYZ", "canonical_value": "Unknown", "make_context": null, "confidence": 0.5, "rationale": "Guessing"}]}'
    groups = [{"source": "x", "raw_make": "XYZ", "raw_model": "A", "count": 1, "vehicle_ids": [5]}]
    suggestions = parse_llm_response(raw, groups=groups)
    assert suggestions == []


def test_discrepancies_page_renders():
    with patch("admin_api.main.get_grouped_discrepancies", return_value=[]):
        with _patched_client() as client:
            resp = client.get("/admin/ui/discrepancies?status=unresolved")
    assert resp.status_code == 200
    assert b"Discrepancies" in resp.content


def test_rules_page_renders():
    with patch("admin_api.main.list_rules", return_value=[]):
        with _patched_client() as client:
            resp = client.get("/admin/ui/rules")
    assert resp.status_code == 200
    assert b"Rules" in resp.content


def test_llm_queue_page_renders():
    with patch("admin_api.main.list_rules", return_value=[]):
        with _patched_client() as client:
            resp = client.get("/admin/ui/llm-queue")
    assert resp.status_code == 200
    assert b"LLM" in resp.content


import os as _os

_DB_URL = _os.environ.get("JUNKYARD_DATABASE_URL", "")

skip_no_db = pytest.mark.skipif(
    not _DB_URL,
    reason="JUNKYARD_DATABASE_URL not set — skipping integration tests",
)


@skip_no_db
def test_integration_discrepancies_returns_200():
    from admin_api.main import app
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get(
            "/admin/discrepancies?status=unresolved",
            headers={"X-Admin-Key": _os.environ.get("ADMIN_API_KEY", "test")},
        )
    assert resp.status_code == 200
    assert "groups" in resp.json()


@skip_no_db
def test_integration_rules_returns_200():
    from admin_api.main import app
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get(
            "/admin/rules",
            headers={"X-Admin-Key": _os.environ.get("ADMIN_API_KEY", "test")},
        )
    assert resp.status_code == 200
    assert "rules" in resp.json()


def test_pi_models_no_filter_returns_all():
    """GET /admin/pi-models with no make param returns all models."""
    with patch("admin_api.discrepancies.get_pi_models_filtered", return_value=["F-150", "Mustang"]) as mock:
        with _patched_client() as client:
            resp = client.get("/admin/pi-models")
    assert resp.status_code == 200
    assert resp.json() == {"models": ["F-150", "Mustang"]}
    mock.assert_called_once_with(None, _admin_main._pi_engine)


def test_pi_models_with_make_filter():
    """GET /admin/pi-models?make=Ford returns filtered models."""
    with patch("admin_api.discrepancies.get_pi_models_filtered", return_value=["F-150"]) as mock:
        with _patched_client() as client:
            resp = client.get("/admin/pi-models?make=Ford")
    assert resp.status_code == 200
    assert resp.json() == {"models": ["F-150"]}
    mock.assert_called_once_with("Ford", _admin_main._pi_engine)


def test_discrepancy_group_has_nhtsa_fields():
    """DiscrepancyGroup accepts nhtsa_make/model/year with None defaults."""
    from admin_api.models import DiscrepancyGroup
    g = DiscrepancyGroup(
        source="x", raw_make="DODGE", raw_model="RAM PICKUP",
        count=5, vehicle_ids=[1],
        best_make_match=None, best_make_score=None,
        best_model_match=None, best_model_score=None,
        candidate_car_id=None,
    )
    assert g.nhtsa_make is None
    assert g.nhtsa_model is None
    assert g.nhtsa_year is None


def test_discrepancy_group_nhtsa_fields_set():
    from admin_api.models import DiscrepancyGroup
    g = DiscrepancyGroup(
        source="x", raw_make="DODGE", raw_model="RAM PICKUP",
        count=5, vehicle_ids=[1],
        best_make_match=None, best_make_score=None,
        best_model_match=None, best_model_score=None,
        candidate_car_id=None,
        nhtsa_make="DODGE", nhtsa_model="RAM 1500", nhtsa_year="2005",
    )
    assert g.nhtsa_make == "DODGE"
    assert g.nhtsa_model == "RAM 1500"
    assert g.nhtsa_year == "2005"


def test_get_grouped_discrepancies_enriches_nhtsa():
    """get_grouped_discrepancies attaches nhtsa_make/model/year from VinCache."""
    from admin_api.discrepancies import get_grouped_discrepancies

    base_group = {
        "source": "pic_n_pull", "raw_make": "DODGE", "raw_model": "RAM PICKUP",
        "count": 5, "min_year": 2001, "max_year": 2008,
        "vehicle_ids": [42],
        "best_make_match": None, "best_make_score": None,
        "best_model_match": None, "best_model_score": None,
        "candidate_car_id": None,
    }

    vin_row = MagicMock()
    vin_row.id = 42
    vin_row.make = "DODGE"
    vin_row.model = "RAM 1500"
    vin_row.model_year = "2003"

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[base_group])))),
        MagicMock(all=MagicMock(return_value=[vin_row])),
    ]

    with patch("admin_api.discrepancies.Session", return_value=mock_session):
        result = get_grouped_discrepancies(MagicMock(), "unresolved")

    assert result[0]["nhtsa_make"] == "DODGE"
    assert result[0]["nhtsa_model"] == "RAM 1500"
    assert result[0]["nhtsa_year"] == "2003"


def test_get_grouped_discrepancies_nhtsa_missing_vin():
    """Groups with no VinCache match get nhtsa fields set to None."""
    from admin_api.discrepancies import get_grouped_discrepancies

    base_group = {
        "source": "x", "raw_make": "DODGE", "raw_model": "RAM",
        "count": 1, "min_year": 2000, "max_year": 2000,
        "vehicle_ids": [99],
        "best_make_match": None, "best_make_score": None,
        "best_model_match": None, "best_model_score": None,
        "candidate_car_id": None,
    }
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[base_group])))),
        MagicMock(all=MagicMock(return_value=[])),  # no VinCache hit
    ]

    with patch("admin_api.discrepancies.Session", return_value=mock_session):
        result = get_grouped_discrepancies(MagicMock(), "unresolved")

    assert result[0]["nhtsa_make"] is None
    assert result[0]["nhtsa_model"] is None
    assert result[0]["nhtsa_year"] is None


def test_create_rule_htmx_discrepancy_context_returns_html():
    """Post from discrepancy form returns HTML success fragment, not JSON."""
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row()):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "DODGE", "canonical_value": "Dodge"},
                headers={"HX-Request": "true", "HX-Target": "rule-form-1"},
            )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert b"Rule saved" in resp.content


def test_create_rule_json_response_without_htmx_header():
    """Non-HTMX POST still returns JSON (API compatibility)."""
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row()):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "DODGE", "canonical_value": "Dodge"},
            )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_create_rule_rejects_unknown_make():
    """POST /admin/rules returns 422 when canonical_value is not a known make."""
    with patch.object(_admin_main, "_pi_engine", MagicMock()), \
         patch("admin_api.rules.get_pi_makes", return_value=["Chevrolet", "Ford"]), \
         patch("admin_api.rules.create_rule") as mock_create:
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "CHEV", "canonical_value": "Chevy"},
            )
    assert resp.status_code == 422
    mock_create.assert_not_called()


def test_create_rule_accepts_valid_make():
    """POST /admin/rules succeeds when canonical_value is a known make."""
    with patch.object(_admin_main, "_pi_engine", MagicMock()), \
         patch("admin_api.rules.get_pi_makes", return_value=["Chevrolet", "Ford"]), \
         patch("admin_api.rules.create_rule", return_value=_make_rule_row(canonical_value="Chevrolet")):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "CHEV", "canonical_value": "Chevrolet"},
            )
    assert resp.status_code == 200


def test_create_rule_skips_validation_without_pi_engine():
    """POST /admin/rules skips canonical validation if PI engine is unavailable."""
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row(canonical_value="NotARealMake")):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "XYZ", "canonical_value": "NotARealMake"},
            )
    assert resp.status_code == 200


def test_create_rule_htmx_rules_page_returns_tr():
    """Post from rules page returns a <tr> fragment for table insertion."""
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row()):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "DODGE", "canonical_value": "Dodge"},
                headers={"HX-Request": "true", "HX-Target": "rules-tbody"},
            )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert b"<tr" in resp.content
