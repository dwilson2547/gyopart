# Phase 5 — Admin Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI web service providing a Jinja2+HTMX admin UI and JSON REST API for reviewing mapping discrepancies, creating normalization rules, approving LLM-suggested rules, and manually assigning car IDs.

**Architecture:** A standalone FastAPI app (`admin_api/`) running on port 8101 with Jinja2 templates + HTMX for the UI. All mutating routes require an `X-Admin-Key` header. The LLM rule suggester is a standalone batch script (`python -m admin_api.llm_suggester`) that queries unresolved discrepancies, calls the Anthropic API, and inserts pending rules. When a rule is approved, FastAPI fires a `BackgroundTasks` job that calls the existing `pipeline.reprocess_job.run_reprocess()`. The admin panel has three views: a grouped discrepancy table (filter by status), an active rules list with creation form, and an LLM suggestion approval queue.

**Tech Stack:** FastAPI, Uvicorn, Jinja2, HTMX (CDN), SQLAlchemy 2.x ORM, psycopg2-binary, Pydantic v2, anthropic SDK, pytest, starlette TestClient

> **User constraint:** NO git commits ever.

---

## Env Vars

| Variable | Used by | Description |
|---|---|---|
| `JUNKYARD_DATABASE_URL` | app + llm_suggester | Postgres connection string |
| `PARTS_DATABASE_URL` | llm_suggester | Parts-interchange DB (canonical makes lookup) |
| `ADMIN_API_KEY` | app | Header value for `X-Admin-Key` auth |
| `ANTHROPIC_API_KEY` | llm_suggester | Anthropic API key |
| `ANTHROPIC_MODEL` | llm_suggester | Default: `claude-haiku-4-5-20251001` |

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `junkyard_platform/admin_api/__init__.py` | Package marker |
| Create | `junkyard_platform/admin_api/main.py` | FastAPI app, lifespan, auth dependency, router registration, template mount |
| Create | `junkyard_platform/admin_api/models.py` | Pydantic request/response models |
| Create | `junkyard_platform/admin_api/discrepancies.py` | Grouped discrepancy query functions + FastAPI router (`/admin/discrepancies`) |
| Create | `junkyard_platform/admin_api/rules.py` | Rule CRUD query functions + FastAPI router (`/admin/rules`, `/admin/vehicles`) |
| Create | `junkyard_platform/admin_api/llm_suggester.py` | Batch job script: queries unresolved groups → Anthropic API → inserts pending rules |
| Create | `junkyard_platform/admin_api/requirements.txt` | Pinned deps |
| Create | `junkyard_platform/admin_api/templates/base.html` | Shared layout: nav, HTMX CDN, CSS |
| Create | `junkyard_platform/admin_api/templates/discrepancies.html` | Grouped discrepancy table with filter tabs, rule-creation and override forms |
| Create | `junkyard_platform/admin_api/templates/rules.html` | Active rule list + manual rule creation form |
| Create | `junkyard_platform/admin_api/templates/llm_queue.html` | Pending LLM suggestion list with approve/reject actions |
| Create | `junkyard_platform/tests/test_admin_api.py` | Unit tests (mocked DB) + integration tests (skipped without DB) |

---

### Task 1: Pydantic Models

**Files:**
- Create: `junkyard_platform/admin_api/__init__.py`
- Create: `junkyard_platform/admin_api/models.py`
- Create: `junkyard_platform/tests/test_admin_api.py`

- [ ] **Step 1: Create `__init__.py`**

Create `junkyard_platform/admin_api/__init__.py` — empty file.

- [ ] **Step 2: Write failing model tests**

Create `junkyard_platform/tests/test_admin_api.py`:

```python
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
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'admin_api'`

- [ ] **Step 4: Create `models.py`**

Create `junkyard_platform/admin_api/models.py`:

```python
from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class DiscrepancyGroup(BaseModel):
    source: str
    raw_make: str | None
    raw_model: str | None
    count: int
    vehicle_ids: list[int]
    best_make_match: str | None
    best_make_score: float | None
    best_model_match: str | None
    best_model_score: float | None
    candidate_car_id: int | None


class DiscrepancyListResponse(BaseModel):
    groups: list[DiscrepancyGroup]
    total: int


class CreateRuleRequest(BaseModel):
    field: str = Field(..., pattern="^(make|model|trim)$")
    rule_type: str = Field(..., pattern="^(exact|prefix|regex)$")
    raw_value: str
    canonical_value: str
    scope: str = Field("global", pattern="^(global|source|location)$")
    source: str | None = None
    location_id: int | None = None
    make_context: str | None = None
    priority: int = Field(100, ge=1, le=1000)


class ManualOverrideRequest(BaseModel):
    car_id: int = Field(..., ge=1)


class RuleResponse(BaseModel):
    id: int
    scope: str
    source: str | None
    location_id: int | None
    field: str
    rule_type: str
    raw_value: str
    canonical_value: str
    make_context: str | None
    priority: int
    is_active: bool
    created_by: str
    created_at: datetime.datetime
    applied_count: int
    llm_confidence: float | None
    llm_rationale: str | None
    approved_at: datetime.datetime | None
    approved_by: str | None


class RuleListResponse(BaseModel):
    rules: list[RuleResponse]


class LlmSuggestion(BaseModel):
    rule_id: int
    field: str
    rule_type: str
    raw_value: str
    canonical_value: str
    make_context: str | None
    llm_confidence: float
    llm_rationale: str
    source: str
    affected_count: int


class LlmSuggestionListResponse(BaseModel):
    suggestions: list[LlmSuggestion]


class ReprocessResponse(BaseModel):
    triggered: bool
    message: str
```

- [ ] **Step 5: Run tests to verify pass**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py -v 2>&1
```

Expected: 6 PASSED.

---

### Task 2: Discrepancy Query Functions + Endpoints

**Files:**
- Create: `junkyard_platform/admin_api/discrepancies.py`
- Modify: `junkyard_platform/tests/test_admin_api.py` (append tests)

The discrepancy list groups by `(vehicle.source, discrepancy.raw_make, discrepancy.raw_model)` filtered by status. Each group shows the count of affected vehicles and the best fuzzy match data (for admin context).

- [ ] **Step 1: Append endpoint tests to the test file**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient


def _make_admin_client():
    with patch("admin_api.main._engine", MagicMock()):
        from admin_api.main import app
        return TestClient(app, headers={"X-Admin-Key": "test-key"})


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


def test_list_discrepancies_requires_auth():
    with patch("admin_api.main._engine", MagicMock()):
        from admin_api.main import app
        client = TestClient(app)
        resp = client.get("/admin/discrepancies?status=unresolved")
    assert resp.status_code == 401


def test_list_discrepancies_returns_groups():
    with patch("admin_api.discrepancies.get_grouped_discrepancies", return_value=_mock_groups()):
        client = _make_admin_client()
        resp = client.get("/admin/discrepancies?status=unresolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["groups"][0]["raw_make"] == "CHEV"
    assert data["groups"][0]["count"] == 47


def test_list_discrepancies_invalid_status_returns_422():
    client = _make_admin_client()
    resp = client.get("/admin/discrepancies?status=bad_value")
    assert resp.status_code == 422


def test_ignore_discrepancy_group():
    with patch("admin_api.discrepancies.ignore_group", return_value=12) as mock_ignore:
        client = _make_admin_client()
        resp = client.post(
            "/admin/discrepancies/ignore",
            json={"source": "pic_n_pull", "raw_make": "CHEV", "raw_model": "SILVERADO 1500"},
        )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 12
    mock_ignore.assert_called_once()
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_list_discrepancies_requires_auth -v 2>&1 | head -15
```

Expected: ImportError — `admin_api.main` doesn't exist yet.

- [ ] **Step 3: Create `discrepancies.py`**

Create `junkyard_platform/admin_api/discrepancies.py`:

```python
from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import MappingDiscrepancy, Vehicle

router = APIRouter(prefix="/admin/discrepancies", tags=["discrepancies"])

VALID_STATUSES = {"unresolved", "pending_rule", "no_match_in_dataset", "ignored"}


def get_grouped_discrepancies(engine: Engine, status: str) -> list[dict]:
    """Group discrepancies by (vehicle.source, raw_make, raw_model) for a given status."""
    with Session(engine) as session:
        rows = session.execute(
            select(
                Vehicle.source,
                MappingDiscrepancy.raw_make,
                MappingDiscrepancy.raw_model,
                func.count().label("count"),
                func.array_agg(MappingDiscrepancy.vehicle_id).label("vehicle_ids"),
                func.max(MappingDiscrepancy.fuzzy_make_match).label("best_make_match"),
                func.max(MappingDiscrepancy.fuzzy_make_score).label("best_make_score"),
                func.max(MappingDiscrepancy.fuzzy_model_match).label("best_model_match"),
                func.max(MappingDiscrepancy.fuzzy_model_score).label("best_model_score"),
                func.max(MappingDiscrepancy.candidate_car_id).label("candidate_car_id"),
            )
            .join(Vehicle, MappingDiscrepancy.vehicle_id == Vehicle.id)
            .where(MappingDiscrepancy.status == status)
            .group_by(Vehicle.source, MappingDiscrepancy.raw_make, MappingDiscrepancy.raw_model)
            .order_by(func.count().desc())
        ).mappings().all()

    return [dict(r) for r in rows]


def ignore_group(engine: Engine, source: str, raw_make: str | None, raw_model: str | None) -> int:
    """Mark all discrepancies in a group as ignored. Returns the count updated."""
    with Session(engine) as session:
        discrepancies = session.execute(
            select(MappingDiscrepancy)
            .join(Vehicle, MappingDiscrepancy.vehicle_id == Vehicle.id)
            .where(
                Vehicle.source == source,
                MappingDiscrepancy.raw_make == raw_make,
                MappingDiscrepancy.raw_model == raw_model,
                MappingDiscrepancy.status.in_(["unresolved", "no_match_in_dataset"]),
            )
        ).scalars().all()
        for d in discrepancies:
            d.status = "ignored"
        session.commit()
    return len(discrepancies)


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("")
def list_discrepancies(
    status: str,
    engine: Engine = Depends(lambda: _get_engine()),
):
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )
    groups = get_grouped_discrepancies(engine, status)
    return {"groups": groups, "total": len(groups)}


class _IgnoreRequest(BaseModel):
    source: str
    raw_make: str | None = None
    raw_model: str | None = None


from pydantic import BaseModel  # noqa: E402  (needed for _IgnoreRequest above)


@router.post("/ignore")
def ignore_discrepancy_group(
    body: _IgnoreRequest,
    engine: Engine = Depends(lambda: _get_engine()),
):
    updated = ignore_group(engine, body.source, body.raw_make, body.raw_model)
    return {"updated": updated}


def _get_engine() -> Engine:
    from admin_api.main import _engine
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return _engine
```

- [ ] **Step 4: Create minimal `main.py` to make tests runnable**

Create `junkyard_platform/admin_api/main.py` (minimal — will be expanded in Task 7):

```python
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from admin_api.discrepancies import router as discrepancies_router

_engine: Engine | None = None
_ADMIN_KEY: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _ADMIN_KEY
    _ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "")
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(url, pool_pre_ping=True, connect_args={"options": "-c statement_timeout=10000"})
    yield
    _engine.dispose()


app = FastAPI(title="Junkyard Admin API", lifespan=lifespan)


@app.middleware("http")
async def require_admin_key(request: Request, call_next):
    if request.url.path.startswith("/admin"):
        key = request.headers.get("X-Admin-Key", "")
        if not _ADMIN_KEY or key != _ADMIN_KEY:
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)


app.include_router(discrepancies_router)
```

- [ ] **Step 5: Fix the `_IgnoreRequest` import order in `discrepancies.py`**

The `BaseModel` import must come before `_IgnoreRequest` is defined. Fix `discrepancies.py` — move the `from pydantic import BaseModel` import to the top of the file with the other imports, and remove the inline import at the bottom:

```python
from __future__ import annotations

import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import MappingDiscrepancy, Vehicle
```

Then remove the duplicate `from pydantic import BaseModel` line at the bottom of the file.

- [ ] **Step 6: Run the discrepancy tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
ADMIN_API_KEY=test-key python -m pytest tests/test_admin_api.py::test_list_discrepancies_requires_auth tests/test_admin_api.py::test_list_discrepancies_returns_groups tests/test_admin_api.py::test_list_discrepancies_invalid_status_returns_422 tests/test_admin_api.py::test_ignore_discrepancy_group -v 2>&1
```

Expected: 4 PASSED (plus 6 earlier model tests = 10 total so far).

---

### Task 3: Rule Management Endpoints

**Files:**
- Create: `junkyard_platform/admin_api/rules.py`
- Modify: `junkyard_platform/admin_api/main.py` (add rules router)
- Modify: `junkyard_platform/tests/test_admin_api.py` (append tests)

Rules flow: manual rules are immediately active. LLM-suggested rules (`created_by="llm_suggested"`) start with `is_active=False` and need explicit approval. Approving a rule sets `is_active=True`, `approved_at`, `approved_by`, and triggers a background reprocess job.

- [ ] **Step 1: Append rule endpoint tests**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
import datetime as _dt


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
        client = _make_admin_client()
        resp = client.get("/admin/rules")
    assert resp.status_code == 200
    assert len(resp.json()["rules"]) == 1


def test_create_rule_manual():
    with patch("admin_api.rules.create_rule", return_value=_make_rule_row()) as mock_create:
        client = _make_admin_client()
        resp = client.post("/admin/rules", json={
            "field": "make",
            "rule_type": "exact",
            "raw_value": "CHEV",
            "canonical_value": "Chevrolet",
        })
    assert resp.status_code == 200
    mock_create.assert_called_once()
    assert resp.json()["is_active"] is True


def test_create_rule_invalid_field_returns_422():
    client = _make_admin_client()
    resp = client.post("/admin/rules", json={
        "field": "engine",  # invalid
        "rule_type": "exact",
        "raw_value": "V8",
        "canonical_value": "V8",
    })
    assert resp.status_code == 422


def test_approve_rule_triggers_reprocess():
    with patch("admin_api.rules.approve_rule", return_value=_make_rule_row(approved_by="admin")):
        with patch("admin_api.rules.run_reprocess") as mock_reprocess:
            client = _make_admin_client()
            resp = client.post("/admin/rules/1/approve", json={"approved_by": "admin"})
    assert resp.status_code == 200
    assert resp.json()["approved_by"] == "admin"


def test_deactivate_rule():
    with patch("admin_api.rules.deactivate_rule", return_value=_make_rule_row(is_active=False)):
        client = _make_admin_client()
        resp = client.post("/admin/rules/1/deactivate")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_list_rules_returns_rules -v 2>&1 | head -15
```

Expected: ImportError — `admin_api.rules` doesn't exist.

- [ ] **Step 3: Create `rules.py`**

Create `junkyard_platform/admin_api/rules.py`:

```python
from __future__ import annotations

import datetime
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import MappingRule
from admin_api.models import CreateRuleRequest, RuleResponse

router = APIRouter(prefix="/admin/rules", tags=["rules"])


def _rule_to_dict(rule: MappingRule) -> dict:
    return {
        "id": rule.id,
        "scope": rule.scope,
        "source": rule.source,
        "location_id": rule.location_id,
        "field": rule.field,
        "rule_type": rule.rule_type,
        "raw_value": rule.raw_value,
        "canonical_value": rule.canonical_value,
        "make_context": rule.make_context,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "created_by": rule.created_by,
        "created_at": rule.created_at,
        "applied_count": rule.applied_count,
        "llm_confidence": rule.llm_confidence,
        "llm_rationale": rule.llm_rationale,
        "approved_at": rule.approved_at,
        "approved_by": rule.approved_by,
    }


def list_rules(engine: Engine, include_inactive: bool = False) -> list[dict]:
    with Session(engine) as session:
        q = select(MappingRule).order_by(MappingRule.field, MappingRule.priority)
        if not include_inactive:
            q = q.where(MappingRule.is_active.is_(True))
        rules = session.execute(q).scalars().all()
    return [_rule_to_dict(r) for r in rules]


def create_rule(engine: Engine, req: CreateRuleRequest) -> dict:
    now = datetime.datetime.utcnow()
    with Session(engine) as session:
        rule = MappingRule(
            scope=req.scope,
            source=req.source,
            location_id=req.location_id,
            field=req.field,
            rule_type=req.rule_type,
            raw_value=req.raw_value,
            canonical_value=req.canonical_value,
            make_context=req.make_context,
            priority=req.priority,
            is_active=True,
            created_by="manual",
            created_at=now,
            applied_count=0,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return _rule_to_dict(rule)


def approve_rule(engine: Engine, rule_id: int, approved_by: str) -> dict:
    now = datetime.datetime.utcnow()
    with Session(engine) as session:
        rule = session.get(MappingRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        rule.is_active = True
        rule.approved_at = now
        rule.approved_by = approved_by
        session.commit()
        return _rule_to_dict(rule)


def deactivate_rule(engine: Engine, rule_id: int) -> dict:
    with Session(engine) as session:
        rule = session.get(MappingRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        rule.is_active = False
        session.commit()
        return _rule_to_dict(rule)


# Background reprocess wrapper (called after rule approval)
def run_reprocess() -> None:
    from pipeline.reprocess_job import run_reprocess as _run
    _run(dry_run=False)


# ── Routes ─────────────────────────────────────────────────────────────────


class _ApproveRequest(BaseModel):
    approved_by: str = "admin"


@router.get("")
def get_rules(
    include_inactive: bool = False,
    engine: Engine = Depends(lambda: _get_engine()),
):
    return {"rules": list_rules(engine, include_inactive)}


@router.post("")
def post_rule(
    body: CreateRuleRequest,
    engine: Engine = Depends(lambda: _get_engine()),
):
    return create_rule(engine, body)


@router.post("/{rule_id}/approve")
def post_approve_rule(
    rule_id: int,
    body: _ApproveRequest,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(lambda: _get_engine()),
):
    result = approve_rule(engine, rule_id, body.approved_by)
    background_tasks.add_task(run_reprocess)
    return result


@router.post("/{rule_id}/deactivate")
def post_deactivate_rule(
    rule_id: int,
    engine: Engine = Depends(lambda: _get_engine()),
):
    return deactivate_rule(engine, rule_id)


def _get_engine() -> Engine:
    from admin_api.main import _engine
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return _engine
```

- [ ] **Step 4: Register the rules router in `main.py`**

Add to `junkyard_platform/admin_api/main.py` after the discrepancies router include:

```python
from admin_api.rules import router as rules_router
# ...
app.include_router(rules_router)
```

The full updated imports section at the top of `main.py`:

```python
from admin_api.discrepancies import router as discrepancies_router
from admin_api.rules import router as rules_router
```

And at the bottom, both routers included:

```python
app.include_router(discrepancies_router)
app.include_router(rules_router)
```

- [ ] **Step 5: Run the rule tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_list_rules_returns_rules tests/test_admin_api.py::test_create_rule_manual tests/test_admin_api.py::test_create_rule_invalid_field_returns_422 tests/test_admin_api.py::test_approve_rule_triggers_reprocess tests/test_admin_api.py::test_deactivate_rule -v 2>&1
```

Expected: 5 PASSED.

---

### Task 4: Manual Car-ID Override Endpoint

**Files:**
- Modify: `junkyard_platform/admin_api/rules.py` (add vehicle override route)
- Modify: `junkyard_platform/tests/test_admin_api.py` (append tests)

Manual override sets `vehicle.car_id` directly and marks the associated discrepancy as resolved. The vehicle is also marked `car_id_resolved=True`, `car_id_method="manual"`, `car_id_confidence=1.0`.

- [ ] **Step 1: Append override tests**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
def test_manual_override_updates_vehicle():
    with patch("admin_api.rules.apply_manual_override", return_value={"vehicle_id": 42, "car_id": 99}) as mock_override:
        client = _make_admin_client()
        resp = client.patch("/admin/vehicles/42/car-id", json={"car_id": 99})
    assert resp.status_code == 200
    assert resp.json()["car_id"] == 99
    mock_override.assert_called_once_with(mock_override.call_args[0][0], 42, 99)


def test_manual_override_invalid_car_id_returns_422():
    client = _make_admin_client()
    resp = client.patch("/admin/vehicles/42/car-id", json={"car_id": 0})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_manual_override_updates_vehicle -v 2>&1 | head -15
```

Expected: 404 (route not registered) or ImportError.

- [ ] **Step 3: Add override function and route to `rules.py`**

Add to `junkyard_platform/admin_api/rules.py` (import `MappingDiscrepancy` and `Vehicle` at top):

```python
from junkyard_common.models import MappingDiscrepancy, MappingRule, Vehicle
```

Add function after `deactivate_rule`:

```python
def apply_manual_override(engine: Engine, vehicle_id: int, car_id: int) -> dict:
    now = datetime.datetime.utcnow()
    with Session(engine) as session:
        vehicle = session.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=404, detail="vehicle not found")
        vehicle.car_id = car_id
        vehicle.car_id_resolved = True
        vehicle.car_id_method = "manual"
        vehicle.car_id_confidence = 1.0

        discrepancy = session.execute(
            select(MappingDiscrepancy).where(MappingDiscrepancy.vehicle_id == vehicle_id)
        ).scalar_one_or_none()
        if discrepancy is not None:
            discrepancy.status = "manual"
            discrepancy.resolved_car_id = car_id
            discrepancy.resolved_at = now

        session.commit()
    return {"vehicle_id": vehicle_id, "car_id": car_id}
```

Add the override router. Since the path is `/admin/vehicles/...` (not `/admin/rules/...`), add a second router in `rules.py`:

```python
vehicles_router = APIRouter(prefix="/admin/vehicles", tags=["vehicles"])

from admin_api.models import ManualOverrideRequest  # noqa: E402


@vehicles_router.patch("/{vehicle_id}/car-id")
def patch_vehicle_car_id(
    vehicle_id: int,
    body: ManualOverrideRequest,
    engine: Engine = Depends(lambda: _get_engine()),
):
    return apply_manual_override(engine, vehicle_id, body.car_id)
```

- [ ] **Step 4: Register the vehicles router in `main.py`**

Update `main.py` imports and includes:

```python
from admin_api.rules import router as rules_router, vehicles_router
# ...
app.include_router(rules_router)
app.include_router(vehicles_router)
```

- [ ] **Step 5: Run override tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_manual_override_updates_vehicle tests/test_admin_api.py::test_manual_override_invalid_car_id_returns_422 -v 2>&1
```

Expected: 2 PASSED. (17 total passing so far.)

---

### Task 5: LLM Rule Suggester Batch Job

**Files:**
- Create: `junkyard_platform/admin_api/llm_suggester.py`
- Modify: `junkyard_platform/tests/test_admin_api.py` (append tests)

The script queries unresolved discrepancy groups, sends them in batches to the Anthropic API, and inserts the suggestions as `MappingRule` rows with `created_by="llm_suggested"`, `is_active=False`. It also updates affected discrepancies to `status="pending_rule"`.

The Anthropic prompt includes canonical make names fetched from the `parts_interchange` DB (to ground the LLM in actual available values).

CLI: `python -m admin_api.llm_suggester [--batch-size 20] [--dry-run]`

- [ ] **Step 1: Append LLM suggester tests**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
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
    raw = '''{"suggestions": [{"group_index": 0, "field": "make", "rule_type": "exact", "raw_value": "CHEV", "canonical_value": "Chevrolet", "make_context": null, "confidence": 0.95, "rationale": "Common abbreviation"}]}'''
    suggestions = parse_llm_response(raw, groups=[{"source": "pic_n_pull", "raw_make": "CHEV", "raw_model": "SILVERADO 1500", "count": 47, "vehicle_ids": [1, 2]}])
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
    raw = '''{"suggestions": [{"group_index": 0, "field": "make", "rule_type": "exact", "raw_value": "XYZ", "canonical_value": "Unknown", "make_context": null, "confidence": 0.5, "rationale": "Guessing"}]}'''
    suggestions = parse_llm_response(raw, groups=[{"source": "x", "raw_make": "XYZ", "raw_model": "A", "count": 1, "vehicle_ids": [5]}])
    assert suggestions == []
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_build_llm_prompt_includes_groups -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'admin_api.llm_suggester'`

- [ ] **Step 3: Create `llm_suggester.py`**

Create `junkyard_platform/admin_api/llm_suggester.py`:

```python
"""
LLM Rule Suggester — batch job that queries unresolved discrepancy groups,
asks the Anthropic API to suggest normalization rules, and inserts them as
pending (is_active=False) MappingRule rows.

CLI:
  python -m admin_api.llm_suggester [--batch-size 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os

import anthropic
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from admin_api.discrepancies import get_grouped_discrepancies
from junkyard_common.db import get_engine
from junkyard_common.models import MappingDiscrepancy, MappingRule

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MIN_CONFIDENCE = 0.80


def fetch_canonical_makes(pi_engine) -> list[str]:
    """Fetch all make names from the parts_interchange DB for grounding the prompt."""
    with pi_engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM make ORDER BY name")).fetchall()
    return [r[0] for r in rows]


def build_prompt(groups: list[dict], canonical_makes: list[str]) -> str:
    makes_str = ", ".join(canonical_makes[:100])  # cap to avoid token overflow
    lines = []
    for i, g in enumerate(groups):
        lines.append(
            f"{i}. source={g['source']!r} make={g['raw_make']!r} model={g['raw_model']!r} count={g['count']}"
        )
    groups_str = "\n".join(lines)

    return f"""You are a vehicle data normalization assistant. Analyze these junkyard inventory groups with non-standard make/model strings and suggest normalization mapping rules.

Canonical car makes in our database: {makes_str}

Groups to normalize (index, source, raw make, raw model, vehicle count):
{groups_str}

For each group you can confidently normalize, respond with a JSON object:
{{
  "suggestions": [
    {{
      "group_index": 0,
      "field": "make",
      "rule_type": "exact",
      "raw_value": "CHEV",
      "canonical_value": "Chevrolet",
      "make_context": null,
      "confidence": 0.95,
      "rationale": "CHEV is a well-known abbreviation for Chevrolet"
    }}
  ]
}}

Rules:
- field: "make", "model", or "trim"
- rule_type: "exact" (full string match), "prefix" (starts-with), or "regex"
- make_context: fill in the canonical make if this is a model/trim rule (helps scope the rule)
- confidence: 0.0-1.0, only include suggestions with confidence >= {MIN_CONFIDENCE}
- You may suggest multiple rules per group (e.g., one for make, one for model)
- Omit groups you cannot confidently normalize
- Respond ONLY with the JSON object, no other text"""


def parse_llm_response(raw_response: str, groups: list[dict]) -> list[dict]:
    """Parse LLM JSON response into a list of suggestion dicts."""
    try:
        data = json.loads(raw_response.strip())
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM response was not valid JSON")
        return []

    results = []
    for s in data.get("suggestions", []):
        if s.get("confidence", 0) < MIN_CONFIDENCE:
            continue
        idx = s.get("group_index")
        if idx is None or idx >= len(groups):
            continue
        group = groups[idx]
        results.append({
            "field": s["field"],
            "rule_type": s["rule_type"],
            "raw_value": s["raw_value"],
            "canonical_value": s["canonical_value"],
            "make_context": s.get("make_context"),
            "llm_confidence": s["confidence"],
            "llm_rationale": s.get("rationale", ""),
            "source": group["source"],
            "affected_vehicle_ids": group["vehicle_ids"],
            "count": group["count"],
        })
    return results


def insert_suggestions(engine, suggestions: list[dict], dry_run: bool) -> int:
    """Insert LLM suggestions as pending MappingRules and mark discrepancies as pending_rule."""
    if dry_run:
        logger.info("[dry-run] Would insert %d suggestions", len(suggestions))
        return len(suggestions)

    now = datetime.datetime.utcnow()
    inserted = 0
    with Session(engine) as session:
        for s in suggestions:
            rule = MappingRule(
                scope="global",
                field=s["field"],
                rule_type=s["rule_type"],
                raw_value=s["raw_value"],
                canonical_value=s["canonical_value"],
                make_context=s.get("make_context"),
                priority=100,
                is_active=False,
                created_by="llm_suggested",
                created_at=now,
                applied_count=0,
                llm_confidence=s["llm_confidence"],
                llm_rationale=s["llm_rationale"],
            )
            session.add(rule)
            session.flush()

            # Mark affected discrepancies as pending_rule
            for vid in s["affected_vehicle_ids"]:
                d = session.execute(
                    select(MappingDiscrepancy).where(
                        MappingDiscrepancy.vehicle_id == vid,
                        MappingDiscrepancy.status == "unresolved",
                    )
                ).scalar_one_or_none()
                if d:
                    d.status = "pending_rule"

            inserted += 1
        session.commit()

    logger.info("Inserted %d pending rule suggestions", inserted)
    return inserted


def run(batch_size: int = 20, dry_run: bool = False) -> None:
    ji_engine = get_engine()
    pi_url = os.environ.get("PARTS_DATABASE_URL")
    pi_engine = create_engine(pi_url) if pi_url else None

    canonical_makes = fetch_canonical_makes(pi_engine) if pi_engine else []
    groups = get_grouped_discrepancies(ji_engine, status="unresolved")

    if not groups:
        logger.info("No unresolved discrepancy groups — nothing to do")
        return

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    total_inserted = 0
    for i in range(0, len(groups), batch_size):
        batch = groups[i : i + batch_size]
        prompt = build_prompt(batch, canonical_makes)
        logger.info("Sending batch %d-%d to LLM...", i, i + len(batch))

        try:
            message = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
        except Exception as exc:
            logger.error("LLM call failed for batch %d: %s", i, exc)
            continue

        suggestions = parse_llm_response(raw, batch)
        logger.info("Batch %d: %d suggestions from LLM", i, len(suggestions))
        total_inserted += insert_suggestions(ji_engine, suggestions, dry_run)

    logger.info("Done. Total suggestions inserted: %d", total_inserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM rule suggester batch job")
    parser.add_argument("--batch-size", type=int, default=20, help="Groups per LLM call")
    parser.add_argument("--dry-run", action="store_true", help="Read-only, no DB writes")
    args = parser.parse_args()
    run(batch_size=args.batch_size, dry_run=args.dry_run)
```

- [ ] **Step 4: Run the LLM suggester tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_build_llm_prompt_includes_groups tests/test_admin_api.py::test_parse_llm_response_valid tests/test_admin_api.py::test_parse_llm_response_invalid_json_returns_empty tests/test_admin_api.py::test_parse_llm_response_low_confidence_filtered -v 2>&1
```

Expected: 4 PASSED.

---

### Task 6: Admin Templates (Jinja2 + HTMX)

**Files:**
- Create: `junkyard_platform/admin_api/templates/base.html`
- Create: `junkyard_platform/admin_api/templates/discrepancies.html`
- Create: `junkyard_platform/admin_api/templates/rules.html`
- Create: `junkyard_platform/admin_api/templates/llm_queue.html`
- Modify: `junkyard_platform/admin_api/main.py` (add template routes)
- Modify: `junkyard_platform/admin_api/discrepancies.py` (add HTML route)
- Modify: `junkyard_platform/admin_api/rules.py` (add HTML routes)
- Modify: `junkyard_platform/tests/test_admin_api.py` (append smoke tests)

The admin UI has three pages served via Jinja2 templates. HTMX handles form submissions and filter tab switching by replacing portions of the page (no full reload). Navigation is a simple top nav with three links.

- [ ] **Step 1: Append template smoke tests**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
def test_discrepancies_page_renders():
    with patch("admin_api.discrepancies.get_grouped_discrepancies", return_value=[]):
        client = _make_admin_client()
        resp = client.get("/admin/ui/discrepancies?status=unresolved")
    assert resp.status_code == 200
    assert b"Discrepancies" in resp.content


def test_rules_page_renders():
    with patch("admin_api.rules.list_rules", return_value=[]):
        client = _make_admin_client()
        resp = client.get("/admin/ui/rules")
    assert resp.status_code == 200
    assert b"Rules" in resp.content


def test_llm_queue_page_renders():
    with patch("admin_api.rules.list_rules", return_value=[]):
        client = _make_admin_client()
        resp = client.get("/admin/ui/llm-queue")
    assert resp.status_code == 200
    assert b"LLM" in resp.content
```

- [ ] **Step 2: Create `templates/base.html`**

Create `junkyard_platform/admin_api/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Junkyard Admin — {% block title %}{% endblock %}</title>
  <script src="https://unpkg.com/htmx.org@1.9.12" integrity="sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2uH1b6QGg8ooR/ksxul0d7UJ9Tp+5gSl5E" crossorigin="anonymous"></script>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #f8f9fa; }
    nav { background: #212529; color: #fff; padding: 0.75rem 1.5rem; display: flex; gap: 1.5rem; align-items: center; }
    nav a { color: #adb5bd; text-decoration: none; }
    nav a.active, nav a:hover { color: #fff; }
    nav strong { color: #fff; margin-right: 1rem; }
    main { padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
    th, td { padding: 0.6rem 0.85rem; text-align: left; border-bottom: 1px solid #dee2e6; font-size: 0.9rem; }
    th { background: #f1f3f5; font-weight: 600; }
    tr:hover td { background: #f8f9fa; }
    .btn { padding: 0.3rem 0.75rem; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
    .btn-primary { background: #0d6efd; color: #fff; }
    .btn-success { background: #198754; color: #fff; }
    .btn-danger  { background: #dc3545; color: #fff; }
    .btn-secondary { background: #6c757d; color: #fff; }
    .tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
    .tab { padding: 0.4rem 1rem; border: 1px solid #dee2e6; border-radius: 4px; cursor: pointer; background: #fff; font-size: 0.9rem; }
    .tab.active { background: #0d6efd; color: #fff; border-color: #0d6efd; }
    .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.78rem; background: #e9ecef; }
    .form-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .form-row label { font-size: 0.85rem; font-weight: 500; }
    .form-row select, .form-row input { padding: 0.3rem 0.5rem; border: 1px solid #ced4da; border-radius: 4px; font-size: 0.85rem; }
    h2 { margin-top: 0; }
    .alert { padding: 0.6rem 1rem; border-radius: 4px; margin-bottom: 1rem; }
    .alert-success { background: #d1e7dd; color: #0a3622; }
    .alert-danger  { background: #f8d7da; color: #58151c; }
  </style>
</head>
<body>
  <nav>
    <strong>Junkyard Admin</strong>
    <a href="/admin/ui/discrepancies?status=unresolved" {% if active == 'discrepancies' %}class="active"{% endif %}>Discrepancies</a>
    <a href="/admin/ui/rules" {% if active == 'rules' %}class="active"{% endif %}>Rules</a>
    <a href="/admin/ui/llm-queue" {% if active == 'llm_queue' %}class="active"{% endif %}>LLM Queue</a>
  </nav>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 3: Create `templates/discrepancies.html`**

Create `junkyard_platform/admin_api/templates/discrepancies.html`:

```html
{% extends "base.html" %}
{% block title %}Discrepancies{% endblock %}
{% block content %}
<h2>Mapping Discrepancies</h2>

<div class="tabs">
  {% for s, label in [("unresolved","Unresolved"),("pending_rule","Pending Rule"),("no_match_in_dataset","No Match"),("ignored","Ignored")] %}
  <button class="tab {% if status == s %}active{% endif %}"
    hx-get="/admin/ui/discrepancies?status={{ s }}"
    hx-target="body"
    hx-push-url="true">{{ label }}</button>
  {% endfor %}
</div>

<div id="discrepancy-table">
{% if not groups %}
  <p>No discrepancies with status <strong>{{ status }}</strong>.</p>
{% else %}
<table>
  <thead>
    <tr>
      <th>Source</th><th>Raw Make</th><th>Raw Model</th><th>Count</th>
      <th>Best Make Match</th><th>Best Model Match</th><th>Actions</th>
    </tr>
  </thead>
  <tbody>
  {% for g in groups %}
  <tr id="group-{{ loop.index }}">
    <td>{{ g.source }}</td>
    <td><code>{{ g.raw_make or '—' }}</code></td>
    <td><code>{{ g.raw_model or '—' }}</code></td>
    <td><span class="badge">{{ g.count }}</span></td>
    <td>{{ g.best_make_match or '—' }} {% if g.best_make_score %}<small>({{ "%.0f"|format(g.best_make_score * 100) }}%)</small>{% endif %}</td>
    <td>{{ g.best_model_match or '—' }} {% if g.best_model_score %}<small>({{ "%.0f"|format(g.best_model_score * 100) }}%)</small>{% endif %}</td>
    <td style="display:flex;gap:0.4rem">
      <button class="btn btn-primary"
        hx-get="/admin/ui/discrepancies/rule-form?source={{ g.source }}&raw_make={{ g.raw_make or '' }}&raw_model={{ g.raw_model or '' }}"
        hx-target="#group-{{ loop.index }}"
        hx-swap="afterend">Rule</button>
      {% if status in ('unresolved', 'no_match_in_dataset') %}
      <button class="btn btn-secondary"
        hx-post="/admin/discrepancies/ignore"
        hx-vals='{"source":"{{ g.source }}","raw_make":"{{ g.raw_make or '' }}","raw_model":"{{ g.raw_model or '' }}"}'
        hx-target="#group-{{ loop.index }}"
        hx-swap="outerHTML"
        hx-headers='{"X-Admin-Key":"{{ admin_key }}"}'>Ignore</button>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
</div>
{% endblock %}
```

- [ ] **Step 4: Create `templates/rules.html`**

Create `junkyard_platform/admin_api/templates/rules.html`:

```html
{% extends "base.html" %}
{% block title %}Rules{% endblock %}
{% block content %}
<h2>Mapping Rules</h2>

<details style="margin-bottom:1rem">
  <summary style="cursor:pointer;font-weight:600">+ Create Rule</summary>
  <form style="margin-top:0.75rem;background:#fff;padding:1rem;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.1)"
    hx-post="/admin/rules"
    hx-target="#rules-table"
    hx-swap="outerHTML"
    hx-headers='{"X-Admin-Key":"{{ admin_key }}","Content-Type":"application/json"}'
    hx-ext="json-enc">
    <div class="form-row">
      <div><label>Field</label><br>
        <select name="field">
          <option value="make">make</option>
          <option value="model">model</option>
          <option value="trim">trim</option>
        </select></div>
      <div><label>Rule Type</label><br>
        <select name="rule_type">
          <option value="exact">exact</option>
          <option value="prefix">prefix</option>
          <option value="regex">regex</option>
        </select></div>
      <div><label>Raw Value</label><br><input name="raw_value" placeholder="CHEV" required></div>
      <div><label>Canonical Value</label><br><input name="canonical_value" placeholder="Chevrolet" required></div>
      <div><label>Make Context</label><br><input name="make_context" placeholder="(optional)"></div>
      <div><label>Scope</label><br>
        <select name="scope">
          <option value="global">global</option>
          <option value="source">source</option>
        </select></div>
      <div><label>Priority</label><br><input name="priority" type="number" value="100" style="width:70px"></div>
    </div>
    <button class="btn btn-success" type="submit">Save Rule</button>
  </form>
</details>

<div id="rules-table">
{% if not rules %}
  <p>No active rules.</p>
{% else %}
<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Raw</th><th>Canonical</th><th>Context</th><th>Scope</th><th>Applied</th><th>Created By</th><th>Actions</th></tr>
  </thead>
  <tbody>
  {% for r in rules %}
  <tr id="rule-{{ r.id }}">
    <td>{{ r.field }}</td>
    <td>{{ r.rule_type }}</td>
    <td><code>{{ r.raw_value }}</code></td>
    <td><code>{{ r.canonical_value }}</code></td>
    <td>{{ r.make_context or '—' }}</td>
    <td>{{ r.scope }}</td>
    <td>{{ r.applied_count }}</td>
    <td>{{ r.created_by }}</td>
    <td>
      <button class="btn btn-danger"
        hx-post="/admin/rules/{{ r.id }}/deactivate"
        hx-target="#rule-{{ r.id }}"
        hx-swap="outerHTML"
        hx-headers='{"X-Admin-Key":"{{ admin_key }}"}'>Deactivate</button>
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Create `templates/llm_queue.html`**

Create `junkyard_platform/admin_api/templates/llm_queue.html`:

```html
{% extends "base.html" %}
{% block title %}LLM Queue{% endblock %}
{% block content %}
<h2>LLM Rule Suggestions</h2>
<p style="color:#6c757d;font-size:0.9rem">Pending rules suggested by the LLM. Review and approve or reject each suggestion. Approving activates the rule and triggers a background reprocess.</p>

{% if not suggestions %}
  <p>No pending LLM suggestions.</p>
{% else %}
<table>
  <thead>
    <tr><th>Source</th><th>Field</th><th>Raw → Canonical</th><th>Type</th><th>Confidence</th><th>Rationale</th><th>Affected</th><th>Actions</th></tr>
  </thead>
  <tbody>
  {% for s in suggestions %}
  <tr id="suggestion-{{ s.rule_id }}">
    <td>{{ s.source }}</td>
    <td>{{ s.field }}</td>
    <td><code>{{ s.raw_value }}</code> → <code>{{ s.canonical_value }}</code></td>
    <td>{{ s.rule_type }}</td>
    <td>{{ "%.0f"|format(s.llm_confidence * 100) }}%</td>
    <td style="max-width:250px;font-size:0.8rem">{{ s.llm_rationale }}</td>
    <td><span class="badge">{{ s.affected_count }}</span></td>
    <td style="display:flex;gap:0.4rem">
      <button class="btn btn-success"
        hx-post="/admin/rules/{{ s.rule_id }}/approve"
        hx-vals='{"approved_by":"admin"}'
        hx-target="#suggestion-{{ s.rule_id }}"
        hx-swap="outerHTML"
        hx-headers='{"X-Admin-Key":"{{ admin_key }}"}'>Approve</button>
      <button class="btn btn-danger"
        hx-post="/admin/rules/{{ s.rule_id }}/deactivate"
        hx-target="#suggestion-{{ s.rule_id }}"
        hx-swap="outerHTML"
        hx-headers='{"X-Admin-Key":"{{ admin_key }}"}'>Reject</button>
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 6: Add UI routes to `discrepancies.py`**

Add to `junkyard_platform/admin_api/discrepancies.py` (at the end, after existing routes):

```python
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        from pathlib import Path
        _templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    return _templates


@router.get("/ui/discrepancies", response_class=HTMLResponse, include_in_schema=False)
def ui_discrepancies(request: Request, status: str = "unresolved"):
    if status not in VALID_STATUSES:
        status = "unresolved"
    engine = _get_engine()
    groups = get_grouped_discrepancies(engine, status)
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    return _get_templates().TemplateResponse(
        "discrepancies.html",
        {"request": request, "groups": groups, "status": status, "active": "discrepancies", "admin_key": admin_key},
    )
```

Note: add `import os` at the top of `discrepancies.py` if not already present.

- [ ] **Step 7: Add UI routes to `rules.py`**

Add to `junkyard_platform/admin_api/rules.py` (at the end):

```python
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request as _Request

_templates: Jinja2Templates | None = None


def _get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        from pathlib import Path
        _templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    return _templates


@router.get("/ui/rules", response_class=HTMLResponse, include_in_schema=False)
def ui_rules(request: _Request):
    engine = _get_engine()
    rules = list_rules(engine)
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    return _get_templates().TemplateResponse(
        "rules.html",
        {"request": request, "rules": rules, "active": "rules", "admin_key": admin_key},
    )


@router.get("/ui/llm-queue", response_class=HTMLResponse, include_in_schema=False)
def ui_llm_queue(request: _Request):
    engine = _get_engine()
    pending = list_rules(engine, include_inactive=True)
    suggestions = [
        {
            "rule_id": r["id"],
            "field": r["field"],
            "rule_type": r["rule_type"],
            "raw_value": r["raw_value"],
            "canonical_value": r["canonical_value"],
            "llm_confidence": r["llm_confidence"] or 0.0,
            "llm_rationale": r["llm_rationale"] or "",
            "source": r["source"] or "global",
            "affected_count": 0,
        }
        for r in pending
        if r["created_by"] == "llm_suggested" and not r["is_active"]
    ]
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    return _get_templates().TemplateResponse(
        "llm_queue.html",
        {"request": request, "suggestions": suggestions, "active": "llm_queue", "admin_key": admin_key},
    )
```

Note: add `import os` to the top of `rules.py` if not already present.

- [ ] **Step 8: Register the UI routes on the main app**

The UI routes are already on the existing routers (`discrepancies_router` uses prefix `/admin/discrepancies`, `rules_router` uses prefix `/admin/rules`). But the UI routes need to be on `/admin/ui/...` paths. Fix by adding them to a shared `ui_router` in `main.py`, or by adjusting the template route paths.

Simplest fix: change the UI route paths to match the router prefix. In `discrepancies.py` change `@router.get("/ui/discrepancies"...)` to `@router.get("/ui"...)` so the full path becomes `/admin/discrepancies/ui`. Then update the nav links accordingly in `base.html`.

Actually, for clarity keep the UI routes at `/admin/ui/...`. Add a new router in `main.py`:

In `main.py`, add:

```python
from fastapi import APIRouter as _APIRouter

_ui_router = _APIRouter(prefix="/admin/ui", tags=["ui"])

@_ui_router.get("/discrepancies", response_class=HTMLResponse, include_in_schema=False)
async def ui_discrepancies_redirect(request: Request, status: str = "unresolved"):
    from admin_api.discrepancies import get_grouped_discrepancies, VALID_STATUSES
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    tmpl = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    if status not in VALID_STATUSES:
        status = "unresolved"
    engine = _engine
    groups = get_grouped_discrepancies(engine, status) if engine else []
    return tmpl.TemplateResponse("discrepancies.html", {
        "request": request, "groups": groups, "status": status,
        "active": "discrepancies", "admin_key": _ADMIN_KEY,
    })

@_ui_router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
async def ui_rules(request: Request):
    from admin_api.rules import list_rules
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    tmpl = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    rules = list_rules(_engine) if _engine else []
    return tmpl.TemplateResponse("rules.html", {
        "request": request, "rules": rules,
        "active": "rules", "admin_key": _ADMIN_KEY,
    })

@_ui_router.get("/llm-queue", response_class=HTMLResponse, include_in_schema=False)
async def ui_llm_queue(request: Request):
    from admin_api.rules import list_rules
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    tmpl = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    pending = list_rules(_engine, include_inactive=True) if _engine else []
    suggestions = [
        {"rule_id": r["id"], "field": r["field"], "rule_type": r["rule_type"],
         "raw_value": r["raw_value"], "canonical_value": r["canonical_value"],
         "llm_confidence": r["llm_confidence"] or 0.0, "llm_rationale": r["llm_rationale"] or "",
         "source": r["source"] or "global", "affected_count": 0}
        for r in pending
        if r["created_by"] == "llm_suggested" and not r["is_active"]
    ]
    return tmpl.TemplateResponse("llm_queue.html", {
        "request": request, "suggestions": suggestions,
        "active": "llm_queue", "admin_key": _ADMIN_KEY,
    })
```

Add `from fastapi.responses import HTMLResponse` and `from fastapi import Request` to `main.py` imports, and register:

```python
app.include_router(_ui_router)
```

Remove the intermediate UI route additions from `discrepancies.py` and `rules.py` (Steps 6 and 7 above) — they are superseded by this `main.py` approach.

- [ ] **Step 9: Run template smoke tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py::test_discrepancies_page_renders tests/test_admin_api.py::test_rules_page_renders tests/test_admin_api.py::test_llm_queue_page_renders -v 2>&1
```

Expected: 3 PASSED.

---

### Task 7: Requirements + Main App Wiring + Startup Smoke Test

**Files:**
- Create: `junkyard_platform/admin_api/requirements.txt`
- Modify: `junkyard_platform/admin_api/main.py` (finalize imports, add root redirect)
- Modify: `junkyard_platform/tests/test_admin_api.py` (add integration tests)

- [ ] **Step 1: Create `requirements.txt`**

Create `junkyard_platform/admin_api/requirements.txt`:

```
fastapi>=0.111
uvicorn[standard]>=0.29
jinja2>=3.1
python-multipart>=0.0.9
sqlalchemy>=2.0
psycopg2-binary>=2.9
pydantic>=2.0
anthropic>=0.26
httpx>=0.27
dwilson-junkyard-common
```

- [ ] **Step 2: Install requirements**

```bash
pip install -r /home/daniel/documents/workspace/junkyard_platform/admin_api/requirements.txt 2>&1 | tail -5
```

- [ ] **Step 3: Finalize `main.py`**

Replace the contents of `junkyard_platform/admin_api/main.py` with the complete, finalized version:

```python
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from admin_api.discrepancies import router as discrepancies_router, get_grouped_discrepancies, VALID_STATUSES
from admin_api.rules import router as rules_router, vehicles_router, list_rules

_engine: Engine | None = None
_ADMIN_KEY: str = ""
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _ADMIN_KEY
    _ADMIN_KEY = os.environ.get("ADMIN_API_KEY", "")
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=10000"},
    )
    yield
    _engine.dispose()


app = FastAPI(title="Junkyard Admin API", lifespan=lifespan)


@app.middleware("http")
async def require_admin_key(request: Request, call_next):
    if request.url.path.startswith("/admin"):
        key = request.headers.get("X-Admin-Key", "")
        if not _ADMIN_KEY or key != _ADMIN_KEY:
            if "text/html" in request.headers.get("accept", ""):
                return JSONResponse(status_code=401, content={"detail": "unauthorized — set X-Admin-Key header"})
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)


_ui_router = APIRouter(prefix="/admin/ui", tags=["ui"])


@_ui_router.get("/discrepancies", response_class=HTMLResponse, include_in_schema=False)
async def ui_discrepancies(request: Request, status: str = "unresolved"):
    if status not in VALID_STATUSES:
        status = "unresolved"
    groups = get_grouped_discrepancies(_engine, status) if _engine else []
    return _templates.TemplateResponse("discrepancies.html", {
        "request": request, "groups": groups, "status": status,
        "active": "discrepancies", "admin_key": _ADMIN_KEY,
    })


@_ui_router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
async def ui_rules(request: Request):
    rules = list_rules(_engine) if _engine else []
    return _templates.TemplateResponse("rules.html", {
        "request": request, "rules": rules,
        "active": "rules", "admin_key": _ADMIN_KEY,
    })


@_ui_router.get("/llm-queue", response_class=HTMLResponse, include_in_schema=False)
async def ui_llm_queue(request: Request):
    pending = list_rules(_engine, include_inactive=True) if _engine else []
    suggestions = [
        {"rule_id": r["id"], "field": r["field"], "rule_type": r["rule_type"],
         "raw_value": r["raw_value"], "canonical_value": r["canonical_value"],
         "llm_confidence": r["llm_confidence"] or 0.0, "llm_rationale": r["llm_rationale"] or "",
         "source": r["source"] or "global", "affected_count": 0}
        for r in pending
        if r["created_by"] == "llm_suggested" and not r["is_active"]
    ]
    return _templates.TemplateResponse("llm_queue.html", {
        "request": request, "suggestions": suggestions,
        "active": "llm_queue", "admin_key": _ADMIN_KEY,
    })


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/admin/ui/discrepancies?status=unresolved")


app.include_router(discrepancies_router)
app.include_router(rules_router)
app.include_router(vehicles_router)
app.include_router(_ui_router)
```

- [ ] **Step 4: Append integration tests**

Append to `junkyard_platform/tests/test_admin_api.py`:

```python
import os as _os

_ADMIN_URL = _os.environ.get("JUNKYARD_DATABASE_URL", "")

skip_no_db = pytest.mark.skipif(
    not _ADMIN_URL,
    reason="JUNKYARD_DATABASE_URL not set — skipping integration tests",
)


@skip_no_db
def test_integration_discrepancies_returns_200():
    from admin_api.main import app
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get("/admin/discrepancies?status=unresolved", headers={"X-Admin-Key": _os.environ.get("ADMIN_API_KEY", "test")})
    assert resp.status_code == 200
    assert "groups" in resp.json()


@skip_no_db
def test_integration_rules_returns_200():
    from admin_api.main import app
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get("/admin/rules", headers={"X-Admin-Key": _os.environ.get("ADMIN_API_KEY", "test")})
    assert resp.status_code == 200
    assert "rules" in resp.json()
```

- [ ] **Step 5: Run all tests**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
python -m pytest tests/test_admin_api.py -v 2>&1
```

Expected: all unit tests PASSED, 2 integration tests SKIPPED.

- [ ] **Step 6: Start the server**

```bash
cd /home/daniel/documents/workspace/junkyard_platform
JUNKYARD_DATABASE_URL="postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/junkyard_inventory" \
ADMIN_API_KEY="localadmin" \
  uvicorn admin_api.main:app --port 8101 2>&1 &
sleep 3
```

Expected: `INFO: Application startup complete.`

- [ ] **Step 7: Smoke test API and UI**

```bash
# Auth required
curl -s http://localhost:8101/admin/discrepancies?status=unresolved
# Expected: {"detail":"unauthorized"}

# With key
curl -s -H "X-Admin-Key: localadmin" "http://localhost:8101/admin/discrepancies?status=unresolved" | python3 -m json.tool
# Expected: {"groups": [...], "total": N}

# UI page
curl -s -H "X-Admin-Key: localadmin" "http://localhost:8101/admin/ui/discrepancies?status=unresolved" | grep -i "discrepancies"
# Expected: HTML containing "Discrepancies"
```

- [ ] **Step 8: Stop the server**

```bash
pkill -f "uvicorn admin_api.main:app" 2>/dev/null; true
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Grouped discrepancy view — `get_grouped_discrepancies()` groups by `(source, raw_make, raw_model)` — Task 2
- [x] Filter modes: unresolved / pending_rule / no_match_in_dataset / ignored — Task 2 (`status` query param, `VALID_STATUSES`)
- [x] Rule creation form, pre-filled from selected discrepancy — Task 6 (discrepancies.html has Rule button → inline form)
- [x] Scope selector on rule creation form — Task 6 (rules.html form has scope dropdown)
- [x] Save rule + triggers re-process — Task 3 (`BackgroundTasks` on approve)
- [x] Manual override: direct car_id assignment — Task 4 (`PATCH /admin/vehicles/{id}/car-id`)
- [x] LLM rule suggester batch job — Task 5 (`llm_suggester.py`)
- [x] LLM suggestion approval queue — Task 6 (llm_queue.html)
- [x] Approved rules trigger re-process — Task 3 (`background_tasks.add_task(run_reprocess)`)
- [x] Auth: API key on all admin routes — Task 2/7 (`require_admin_key` middleware)
- [x] Ignore discrepancy group — Task 2 (`POST /admin/discrepancies/ignore`)

**Placeholder scan:** No TBD, no "similar to above". All code blocks are complete.

**Type consistency:**
- `get_grouped_discrepancies(engine, status)` → `list[dict]` — used consistently in Task 2 routes and Task 6 UI routes
- `list_rules(engine, include_inactive)` → `list[dict]` — used consistently in Task 3 and Task 6
- `apply_manual_override(engine, vehicle_id, car_id)` → `dict` — used in Task 4 route
- `parse_llm_response(raw, groups)` → `list[dict]` — used in Task 5 `run()` function
- `run_reprocess()` (no args wrapper) → called by `background_tasks.add_task` in Task 3
