# Admin Discrepancy UI — 4 Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four issues in the admin discrepancy/rules UI: broken rule creation HTMX response, missing field-level match indicators, free-text canonical value inputs that allow invalid rules, and complete absence of NHTSA VIN decode data in the discrepancy workflow.

**Architecture:** Backend changes are additive (new function, new endpoint, enriched query, HTML response branch in post_rule). Template changes replace two files entirely. All four improvements are independent but share a single commit cadence — each task is self-contained and tested before committing.

**Tech Stack:** FastAPI, SQLAlchemy core (Table objects from pi_schema.py), Jinja2 templates, HTMX 1.9.12, vanilla JS fetch API.

---

## File Map

| File | Change |
|------|--------|
| `admin_api/discrepancies.py` | Add `get_pi_models_filtered()`, add VinCache enrichment to `get_grouped_discrepancies()`, add `GET /admin/pi-models` route |
| `admin_api/rules.py` | Add `_get_pi_engine()` dep, add canonical validation to `post_rule()`, return HTML fragment when HX-Request present |
| `admin_api/models.py` | Add `nhtsa_make/model/year` fields to `DiscrepancyGroup` |
| `admin_api/templates/_rule_row.html` | **New** — partial `<tr>` used by rules.html and returned as HTMX fragment |
| `admin_api/templates/discrepancies.html` | NHTSA column, split fuzzy-guess indicators, canonical select, Use NHTSA buttons, fix HTMX target |
| `admin_api/templates/rules.html` | Canonical select + dynamic model fetch, fix HTMX target |
| `tests/test_admin_api.py` | Tests for new endpoint, NHTSA enrichment, HTML response, canonical validation |

---

## Task 1: Add `get_pi_models_filtered`, the `/admin/pi-models` endpoint, `_get_pi_engine` dep, and NHTSA fields on DiscrepancyGroup

**Files:**
- Modify: `admin_api/discrepancies.py`
- Modify: `admin_api/models.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_admin_api.py`:

```python
def test_pi_models_no_filter_returns_all():
    """GET /admin/pi-models with no make param returns all models."""
    from admin_api.discrepancies import get_pi_models_all
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /home/daniel/documents/workspace/gyopart/junkyard-platform
python -m pytest tests/test_admin_api.py::test_pi_models_no_filter_returns_all tests/test_admin_api.py::test_discrepancy_group_has_nhtsa_fields -v
```
Expected: FAIL — `get_pi_models_filtered` not defined, `DiscrepancyGroup` has no nhtsa fields.

- [ ] **Step 3: Add NHTSA fields to DiscrepancyGroup in `admin_api/models.py`**

```python
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
    nhtsa_make: str | None = None
    nhtsa_model: str | None = None
    nhtsa_year: str | None = None
```

- [ ] **Step 4: Add `get_pi_models_filtered` and the route to `admin_api/discrepancies.py`**

Add the function after `get_pi_models_all`:

```python
def get_pi_models_filtered(make: str | None, pi_engine: Engine | None) -> list[str]:
    if pi_engine is None:
        return []
    with pi_engine.connect() as conn:
        if make:
            rows = conn.execute(
                select(pi_model_table.c.name)
                .join(pi_make_table, pi_model_table.c.make_id == pi_make_table.c.id)
                .where(func.lower(pi_make_table.c.name) == func.lower(make))
                .order_by(pi_model_table.c.name)
            ).all()
        else:
            rows = conn.execute(
                select(pi_model_table.c.name).distinct().order_by(pi_model_table.c.name)
            ).all()
    return [r[0] for r in rows]
```

Also add `func` to the sqlalchemy import at the top of `discrepancies.py` (it's already there for the grouped query) and add `pi_make_table` to the pipeline import line:

```python
from pipeline.pi_schema import pi_make_table, pi_model_table
```

(This import already exists — `pi_make_table` is used by `get_pi_makes`. Confirm it includes both.)

Add the route at the bottom of `discrepancies.py`, before the existing `@router.post("/ignore")`:

```python
def _get_pi_engine() -> Engine | None:
    from admin_api.main import _pi_engine
    return _pi_engine


@router.get("/pi-models")
def get_models_endpoint(make: str | None = None, pi_engine: Engine | None = Depends(_get_pi_engine)):
    return {"models": get_pi_models_filtered(make, pi_engine)}
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_admin_api.py::test_pi_models_no_filter_returns_all tests/test_admin_api.py::test_pi_models_with_make_filter tests/test_admin_api.py::test_discrepancy_group_has_nhtsa_fields tests/test_admin_api.py::test_discrepancy_group_nhtsa_fields_set -v
```
Expected: PASS (4/4)

- [ ] **Step 6: Run full suite to check for regressions**

```
python -m pytest tests/test_admin_api.py -v -k "not integration"
```
Expected: all non-integration tests pass.

- [ ] **Step 7: Commit**

```bash
git add admin_api/models.py admin_api/discrepancies.py tests/test_admin_api.py
git commit -m "feat(admin): add nhtsa fields to DiscrepancyGroup and pi-models endpoint"
```

---

## Task 2: Enrich `get_grouped_discrepancies` with NHTSA data

**Files:**
- Modify: `admin_api/discrepancies.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_admin_api.py`:

```python
def test_get_grouped_discrepancies_enriches_nhtsa(tmp_path):
    """get_grouped_discrepancies attaches nhtsa_make/model/year from VinCache."""
    from unittest.mock import MagicMock, patch
    from admin_api.discrepancies import get_grouped_discrepancies

    base_group = {
        "source": "pic_n_pull", "raw_make": "DODGE", "raw_model": "RAM PICKUP",
        "count": 5, "min_year": 2001, "max_year": 2008,
        "vehicle_ids": [42],
        "best_make_match": None, "best_make_score": None,
        "best_model_match": None, "best_model_score": None,
        "candidate_car_id": None,
    }

    # Simulate the first query returning the base group
    mock_mapping = MagicMock()
    mock_mapping.__iter__ = MagicMock(return_value=iter([base_group]))

    # Simulate VinCache join returning NHTSA data for vehicle_id=42
    nhtsa_row = MagicMock()
    nhtsa_row.__getitem__ = lambda self, i: [42, "DODGE", "RAM 1500", "2003"][i]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[base_group])))),
        MagicMock(all=MagicMock(return_value=[(42, "DODGE", "RAM 1500", "2003")])),
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_admin_api.py::test_get_grouped_discrepancies_enriches_nhtsa tests/test_admin_api.py::test_get_grouped_discrepancies_nhtsa_missing_vin -v
```
Expected: FAIL — no nhtsa_ keys in returned dicts.

- [ ] **Step 3: Implement NHTSA enrichment in `get_grouped_discrepancies`**

In `admin_api/discrepancies.py`, add `VinCache` to the junkyard_common import:

```python
from junkyard_common.models import MappingDiscrepancy, Vehicle, VinCache
```

Replace the existing `get_grouped_discrepancies` function body:

```python
def get_grouped_discrepancies(engine: Engine, status: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.execute(
            select(
                Vehicle.source,
                MappingDiscrepancy.raw_make,
                MappingDiscrepancy.raw_model,
                func.count().label("count"),
                func.min(Vehicle.year).label("min_year"),
                func.max(Vehicle.year).label("max_year"),
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

        result = []
        for r in rows:
            d = dict(r)
            d["vehicle_ids"] = list(d.get("vehicle_ids") or [])
            result.append(d)

        # Enrich each group with NHTSA decode from a sample vehicle's VIN
        sample_ids = [g["vehicle_ids"][0] for g in result if g["vehicle_ids"]]
        if sample_ids:
            vin_rows = session.execute(
                select(Vehicle.id, VinCache.make, VinCache.model, VinCache.model_year)
                .join(VinCache, Vehicle.vin == VinCache.vin)
                .where(Vehicle.id.in_(sample_ids))
            ).all()
            nhtsa_by_id = {row[0]: (row[1], row[2], row[3]) for row in vin_rows}
        else:
            nhtsa_by_id = {}

        for g in result:
            sample_id = g["vehicle_ids"][0] if g["vehicle_ids"] else None
            nhtsa = nhtsa_by_id.get(sample_id) if sample_id is not None else None
            g["nhtsa_make"] = nhtsa[0] if nhtsa else None
            g["nhtsa_model"] = nhtsa[1] if nhtsa else None
            g["nhtsa_year"] = nhtsa[2] if nhtsa else None

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_admin_api.py::test_get_grouped_discrepancies_enriches_nhtsa tests/test_admin_api.py::test_get_grouped_discrepancies_nhtsa_missing_vin -v
```
Expected: PASS

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/test_admin_api.py -v -k "not integration"
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add admin_api/discrepancies.py tests/test_admin_api.py
git commit -m "feat(admin): enrich discrepancy groups with NHTSA VIN decode data"
```

---

## Task 3: Fix `post_rule` — HTMX HTML response + canonical validation

**Files:**
- Modify: `admin_api/rules.py`
- Test: `tests/test_admin_api.py`

The `post_rule` endpoint currently returns a plain JSON dict. HTMX has no instruction for what to do with it so the response is silently discarded — that is the "does nothing" bug. Fix: when `HX-Request` header is present, return an HTML fragment. The discrepancy form targets its own form row (`#rule-form-N`) for replacement; the rules page form targets `#rules-tbody` for row insertion. Canonical validation is added when the PI engine is available, using `get_pi_makes` and `get_pi_models_filtered` imported from `discrepancies.py`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_admin_api.py`:

```python
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
    def mock_get_pi_engine():
        return MagicMock()

    with patch("admin_api.rules._get_pi_engine", return_value=MagicMock()), \
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
    with patch("admin_api.rules._get_pi_engine", return_value=MagicMock()), \
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
    with patch("admin_api.rules._get_pi_engine", return_value=None), \
         patch("admin_api.rules.create_rule", return_value=_make_rule_row(canonical_value="NotARealMake")):
        with _patched_client() as client:
            resp = client.post(
                "/admin/rules",
                data={"field": "make", "rule_type": "exact", "raw_value": "XYZ", "canonical_value": "NotARealMake"},
            )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest tests/test_admin_api.py::test_create_rule_htmx_discrepancy_context_returns_html tests/test_admin_api.py::test_create_rule_rejects_unknown_make -v
```
Expected: FAIL

- [ ] **Step 3: Update `admin_api/rules.py`**

Add imports at top:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from admin_api.discrepancies import get_pi_makes, get_pi_models_all, get_pi_models_filtered
```

Add `_get_pi_engine` below `_get_engine`:

```python
def _get_pi_engine() -> Engine | None:
    from admin_api.main import _pi_engine
    return _pi_engine
```

Replace the `post_rule` route:

```python
@router.post("")
def post_rule(
    request: Request,
    field: str = Form(...),
    rule_type: str = Form(...),
    raw_value: str = Form(...),
    canonical_value: str = Form(...),
    scope: str = Form("global"),
    source: str | None = Form(None),
    location_id: int | None = Form(None),
    make_context: str | None = Form(None),
    priority: int = Form(100),
    engine: Engine = Depends(_get_engine),
    pi_engine: Engine | None = Depends(_get_pi_engine),
):
    try:
        req = CreateRuleRequest(
            field=field, rule_type=rule_type, raw_value=raw_value,
            canonical_value=canonical_value, scope=scope, source=source,
            location_id=location_id, make_context=make_context, priority=priority,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    if pi_engine is not None:
        if req.field == "make":
            valid = get_pi_makes(pi_engine)
            if req.canonical_value not in valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown make: {req.canonical_value!r}. Must be an exact PI make name.",
                )
        elif req.field == "model":
            valid = get_pi_models_filtered(req.make_context, pi_engine) if req.make_context else get_pi_models_all(pi_engine)
            if req.canonical_value not in valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown model: {req.canonical_value!r}.",
                )

    rule = create_rule(engine, req)

    if request.headers.get("HX-Request"):
        hx_target = request.headers.get("HX-Target", "")
        if hx_target == "rules-tbody":
            from fastapi.templating import Jinja2Templates
            from pathlib import Path
            templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
            return templates.TemplateResponse(request, "_rule_row.html", {"rule": rule})
        # discrepancy form or other HTMX context — return inline success
        return HTMLResponse(
            f'<tr id="rule-form-{hx_target.replace("rule-form-", "")}" style="display:none">'
            f'<td colspan="8"><span style="color:#28a745;font-size:0.85rem">'
            f'✓ Rule saved: <code>{rule["raw_value"]}</code> → <code>{rule["canonical_value"]}</code>'
            f'</span></td></tr>'
        )

    return rule
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_admin_api.py::test_create_rule_htmx_discrepancy_context_returns_html tests/test_admin_api.py::test_create_rule_htmx_rules_page_returns_tr tests/test_admin_api.py::test_create_rule_json_response_without_htmx_header tests/test_admin_api.py::test_create_rule_rejects_unknown_make tests/test_admin_api.py::test_create_rule_accepts_valid_make tests/test_admin_api.py::test_create_rule_skips_validation_without_pi_engine -v
```
Expected: PASS (6/6) — the `_rule_row.html` test will fail until Task 4 creates the template; run it after Task 4.

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/test_admin_api.py -v -k "not integration"
```
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add admin_api/rules.py tests/test_admin_api.py
git commit -m "feat(admin): fix post_rule HTMX response and add canonical value validation"
```

---

## Task 4: Create `_rule_row.html` partial template

**Files:**
- Create: `admin_api/templates/_rule_row.html`

This partial is both `{% include %}`-d by `rules.html` and rendered directly by `post_rule` when `HX-Target == rules-tbody`. The variable name must be `rule` (a dict with keys matching `_rule_to_dict`).

- [ ] **Step 1: Create the file**

`admin_api/templates/_rule_row.html`:

```html
<tr id="rule-{{ rule.id }}">
  <td>{{ rule.field }}</td>
  <td>{{ rule.rule_type }}</td>
  <td><code>{{ rule.raw_value }}</code></td>
  <td><code>{{ rule.canonical_value }}</code></td>
  <td>{{ rule.make_context or '—' }}</td>
  <td>{{ rule.scope }}</td>
  <td>{{ rule.applied_count }}</td>
  <td>{{ rule.created_by }}</td>
  <td>
    <button class="btn btn-danger"
      hx-post="/admin/rules/{{ rule.id }}/deactivate"
      hx-target="#rule-{{ rule.id }}"
      hx-swap="outerHTML">Deactivate</button>
  </td>
</tr>
```

- [ ] **Step 2: Verify the HTMX-rules-page test now passes**

```
python -m pytest tests/test_admin_api.py::test_create_rule_htmx_rules_page_returns_tr -v
```
Expected: PASS — template now exists and renders.

- [ ] **Step 3: Commit**

```bash
git add admin_api/templates/_rule_row.html
git commit -m "feat(admin): add _rule_row.html partial for HTMX rule insertion"
```

---

## Task 5: Rewrite `discrepancies.html`

**Files:**
- Modify: `admin_api/templates/discrepancies.html`

Four changes in one template rewrite:
1. **NHTSA column** — new `<th>NHTSA Decode</th>` showing `nhtsa_make / nhtsa_model (nhtsa_year)` or `—`.
2. **Split fuzzy indicators** — replace single "Fuzzy Guess" cell with two labelled status cells (make / model), each showing the match + score or a red ✗.
3. **Canonical `<select>` for make** — replace `<input list="pi-makes">` with a `<select>` pre-populated from `pi_makes`; for model, fetch dynamically from `/admin/pi-models`; for trim, fall back to `<input>`.
4. **"Use NHTSA" buttons** — two new buttons next to Save/Cancel that pre-fill the form from NHTSA decoded values; shown only when NHTSA data is present.
5. **Fix HTMX target** — form already targets `#rule-form-N` with `outerHTML` swap; this is correct for the success response added in Task 3. No change needed.

- [ ] **Step 1: Replace `admin_api/templates/discrepancies.html`**

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

{% if not groups %}
  <p>No discrepancies with status <strong>{{ status }}</strong>.</p>
{% else %}
<table>
  <thead>
    <tr>
      <th>Source</th><th>Raw Make</th><th>Raw Model</th><th>Years</th><th>Count</th>
      <th>NHTSA Decode</th>
      <th>Make Match</th><th>Model Match</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody>
  {% for g in groups %}
  <tr id="group-{{ loop.index }}">
    <td>{{ g.source }}</td>
    <td><code>{{ g.raw_make or '—' }}</code></td>
    <td><code>{{ g.raw_model or '—' }}</code></td>
    <td style="white-space:nowrap">
      {% if g.min_year and g.max_year %}
        {% if g.min_year == g.max_year %}{{ g.min_year }}
        {% else %}{{ g.min_year }}–{{ g.max_year }}{% endif %}
      {% else %}—{% endif %}
    </td>
    <td><span class="badge">{{ g.count }}</span></td>
    <td style="font-size:0.85rem">
      {% if g.nhtsa_make %}
        <code>{{ g.nhtsa_make }}</code>
        {% if g.nhtsa_model %} / <code>{{ g.nhtsa_model }}</code>{% endif %}
        {% if g.nhtsa_year %} <small style="color:#888">({{ g.nhtsa_year }})</small>{% endif %}
      {% else %}
        <span style="color:#aaa">—</span>
      {% endif %}
    </td>
    <td style="font-size:0.85rem">
      {% if g.best_make_match %}
        <span style="color:#28a745">✓</span> {{ g.best_make_match }}
        <small style="color:#888">({{ "%.0f"|format(g.best_make_score * 100) }}%)</small>
      {% else %}
        <span style="color:#dc3545">✗</span> <span style="color:#aaa">no match</span>
      {% endif %}
    </td>
    <td style="font-size:0.85rem">
      {% if g.best_model_match %}
        <span style="color:#28a745">✓</span> {{ g.best_model_match }}
        <small style="color:#888">({{ "%.0f"|format(g.best_model_score * 100) }}%)</small>
      {% else %}
        <span style="color:#dc3545">✗</span> <span style="color:#aaa">no match</span>
      {% endif %}
    </td>
    <td style="display:flex;gap:0.4rem;flex-wrap:wrap">
      {% if status in ('unresolved', 'no_match_in_dataset') %}
      <button class="btn btn-primary" style="font-size:0.8rem"
        onclick="toggleRuleForm({{ loop.index }}, '{{ g.source }}', {{ g.raw_make|tojson }}, {{ g.raw_model|tojson }}, {{ g.nhtsa_make|tojson }}, {{ g.nhtsa_model|tojson }})">
        Create Rule
      </button>
      <button class="btn btn-secondary" style="font-size:0.8rem"
        hx-post="/admin/discrepancies/ignore"
        hx-vals="{{ {'source': g.source, 'raw_make': g.raw_make or '', 'raw_model': g.raw_model or ''} | tojson }}"
        hx-target="#group-{{ loop.index }}"
        hx-swap="outerHTML">Ignore</button>
      {% endif %}
    </td>
  </tr>
  <tr id="rule-form-{{ loop.index }}" style="display:none;background:#f8f9fa">
    <td colspan="9" style="padding:1rem">
      <form hx-post="/admin/rules"
            hx-target="rule-form-{{ loop.index }}"
            hx-swap="outerHTML"
            style="display:flex;gap:0.75rem;flex-wrap:wrap;align-items:flex-end">
        <div>
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Field</label>
          <select name="field" id="field-{{ loop.index }}"
            onchange="onDiscrepancyFieldChange({{ loop.index }}, this.value)">
            <option value="make">make</option>
            <option value="model">model</option>
            <option value="trim">trim</option>
          </select>
        </div>
        <div>
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Rule Type</label>
          <select name="rule_type">
            <option value="exact">exact</option>
            <option value="prefix">prefix</option>
            <option value="regex">regex</option>
          </select>
        </div>
        <div>
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Raw Value</label>
          <input name="raw_value" id="raw-value-{{ loop.index }}" required style="width:140px">
        </div>
        <div id="canonical-wrap-{{ loop.index }}">
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Canonical Value</label>
          <select name="canonical_value" id="canonical-{{ loop.index }}" required style="width:180px">
            {% for m in pi_makes %}<option value="{{ m }}">{{ m }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Scope</label>
          <select name="scope" id="scope-{{ loop.index }}">
            <option value="global">global</option>
            <option value="source">source</option>
          </select>
        </div>
        <div>
          <label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Make Context</label>
          <input name="make_context" id="make-context-{{ loop.index }}" placeholder="(optional)" style="width:120px">
        </div>
        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;align-items:flex-end">
          <button class="btn btn-success" type="submit">Save</button>
          {% if g.nhtsa_make %}
          <button class="btn btn-secondary" type="button" style="font-size:0.75rem"
            onclick="useNhtsaMake({{ loop.index }}, {{ g.raw_make|tojson }}, {{ g.nhtsa_make|tojson }})">
            ↑ NHTSA Make
          </button>
          {% endif %}
          {% if g.nhtsa_model %}
          <button class="btn btn-secondary" type="button" style="font-size:0.75rem"
            onclick="useNhtsaModel({{ loop.index }}, {{ g.raw_model|tojson }}, {{ g.nhtsa_make|tojson }}, {{ g.nhtsa_model|tojson }})">
            ↑ NHTSA Model
          </button>
          {% endif %}
          <button class="btn btn-secondary" type="button"
            onclick="document.getElementById('rule-form-{{ loop.index }}').style.display='none'">
            Cancel
          </button>
        </div>
      </form>
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}

<script>
const PI_MAKES_OPTIONS = `{% for m in pi_makes %}<option value="{{ m }}">{{ m }}</option>
{% endfor %}`;

function toggleRuleForm(idx, source, rawMake, rawModel, nhtsaMake, nhtsaModel) {
  var row = document.getElementById('rule-form-' + idx);
  if (row.style.display === 'none') {
    row.style.display = '';
    document.getElementById('raw-value-' + idx).value = rawMake || rawModel || '';
    document.getElementById('scope-' + idx).value = source ? 'source' : 'global';
    var field = document.getElementById('field-' + idx);
    if (rawMake && !rawModel) { field.value = 'make'; }
    else if (rawModel) { field.value = 'model'; }
    onDiscrepancyFieldChange(idx, field.value);
  } else {
    row.style.display = 'none';
  }
}

function onDiscrepancyFieldChange(idx, field) {
  var wrap = document.getElementById('canonical-wrap-' + idx);
  if (field === 'make') {
    wrap.innerHTML = '<label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Canonical Value</label>'
      + '<select name="canonical_value" id="canonical-' + idx + '" required style="width:180px">'
      + PI_MAKES_OPTIONS + '</select>';
  } else if (field === 'model') {
    var makeCtx = document.getElementById('make-context-' + idx).value;
    wrap.innerHTML = '<label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Canonical Value</label>'
      + '<select name="canonical_value" id="canonical-' + idx + '" required style="width:180px">'
      + '<option value="">Loading…</option></select>';
    loadDiscrepancyModelOptions(idx, makeCtx);
  } else {
    wrap.innerHTML = '<label style="display:block;font-size:0.8rem;font-weight:600;margin-bottom:2px">Canonical Value</label>'
      + '<input name="canonical_value" id="canonical-' + idx + '" placeholder="canonical trim" required style="width:180px">';
  }
}

async function loadDiscrepancyModelOptions(idx, make) {
  var url = make ? '/admin/pi-models?make=' + encodeURIComponent(make) : '/admin/pi-models';
  var resp = await fetch(url);
  var data = await resp.json();
  var sel = document.getElementById('canonical-' + idx);
  if (sel) {
    sel.innerHTML = data.models.map(function(m) {
      return '<option value="' + m.replace(/"/g, '&quot;') + '">' + m + '</option>';
    }).join('');
  }
}

function useNhtsaMake(idx, rawMake, nhtsaMake) {
  document.getElementById('field-' + idx).value = 'make';
  document.getElementById('raw-value-' + idx).value = rawMake || '';
  onDiscrepancyFieldChange(idx, 'make');
  // Wait for select to render, then set value
  setTimeout(function() {
    var sel = document.getElementById('canonical-' + idx);
    if (sel) sel.value = nhtsaMake;
  }, 0);
}

async function useNhtsaModel(idx, rawModel, nhtsaMake, nhtsaModel) {
  document.getElementById('field-' + idx).value = 'model';
  document.getElementById('raw-value-' + idx).value = rawModel || '';
  document.getElementById('make-context-' + idx).value = nhtsaMake || '';
  onDiscrepancyFieldChange(idx, 'model');
  // Load models filtered by NHTSA make, then select NHTSA model
  var url = nhtsaMake ? '/admin/pi-models?make=' + encodeURIComponent(nhtsaMake) : '/admin/pi-models';
  var resp = await fetch(url);
  var data = await resp.json();
  var sel = document.getElementById('canonical-' + idx);
  if (sel) {
    sel.innerHTML = data.models.map(function(m) {
      return '<option value="' + m.replace(/"/g, '&quot;') + '">' + m + '</option>';
    }).join('');
    sel.value = nhtsaModel || '';
  }
}
</script>
{% endblock %}
```

- [ ] **Step 2: Verify the discrepancy page still renders**

```
python -m pytest tests/test_admin_api.py::test_discrepancies_page_renders -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add admin_api/templates/discrepancies.html
git commit -m "feat(admin): NHTSA column, split match indicators, canonical select, Use NHTSA buttons"
```

---

## Task 6: Rewrite `rules.html` — canonical select + dynamic model loading

**Files:**
- Modify: `admin_api/templates/rules.html`

The rules page form's canonical value is currently a free-text `<input list="pi-makes">`. Replace with the same dynamic select pattern: `<select>` for make (strict), `<select>` populated via fetch for model, free `<input>` for trim. Also fix the form's `hx-target` and `hx-swap` to insert the new `<tr>` at the top of the tbody via `_rule_row.html`.

- [ ] **Step 1: Replace `admin_api/templates/rules.html`**

```html
{% extends "base.html" %}
{% block title %}Rules{% endblock %}
{% block content %}
<h2>Mapping Rules</h2>

<details style="margin-bottom:1rem">
  <summary style="cursor:pointer;font-weight:600">+ Create Rule</summary>
  <form style="margin-top:0.75rem;background:#fff;padding:1rem;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.1)"
    hx-post="/admin/rules"
    hx-target="rules-tbody"
    hx-swap="afterbegin">
    <div class="form-row">
      <div><label>Field</label><br>
        <select name="field" id="rules-field" onchange="onRulesFieldChange(this.value)">
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
      <div id="rules-canonical-wrap">
        <label>Canonical Value</label><br>
        <select name="canonical_value" id="rules-canonical" required style="min-width:160px">
          {% for m in pi_makes %}<option value="{{ m }}">{{ m }}</option>{% endfor %}
        </select>
      </div>
      <div><label>Make Context</label><br>
        <input name="make_context" id="rules-make-context" placeholder="(optional)"
          oninput="onRulesMakeContextChange(this.value)">
      </div>
      <div><label>Scope</label><br>
        <select name="scope">
          <option value="global">global</option>
          <option value="source">source</option>
        </select></div>
      <div><label>Priority</label><br>
        <input name="priority" type="number" value="100" style="width:70px"></div>
    </div>
    <button class="btn btn-success" type="submit">Save Rule</button>
  </form>
</details>

<table>
  <thead>
    <tr><th>Field</th><th>Type</th><th>Raw</th><th>Canonical</th><th>Context</th><th>Scope</th><th>Applied</th><th>Created By</th><th>Actions</th></tr>
  </thead>
  <tbody id="rules-tbody">
  {% for rule in rules %}
  {% include "_rule_row.html" %}
  {% endfor %}
  </tbody>
</table>
{% if not rules %}
  <p id="rules-empty">No active rules.</p>
{% endif %}

<script>
const PI_MAKES_OPTIONS_RULES = `{% for m in pi_makes %}<option value="{{ m }}">{{ m }}</option>
{% endfor %}`;

function onRulesFieldChange(field) {
  var wrap = document.getElementById('rules-canonical-wrap');
  if (field === 'make') {
    wrap.innerHTML = '<label>Canonical Value</label><br>'
      + '<select name="canonical_value" id="rules-canonical" required style="min-width:160px">'
      + PI_MAKES_OPTIONS_RULES + '</select>';
  } else if (field === 'model') {
    var makeCtx = document.getElementById('rules-make-context').value;
    wrap.innerHTML = '<label>Canonical Value</label><br>'
      + '<select name="canonical_value" id="rules-canonical" required style="min-width:160px">'
      + '<option value="">Loading…</option></select>';
    loadRulesModelOptions(makeCtx);
  } else {
    wrap.innerHTML = '<label>Canonical Value</label><br>'
      + '<input name="canonical_value" id="rules-canonical" placeholder="canonical trim" required style="min-width:160px">';
  }
}

async function loadRulesModelOptions(make) {
  var url = make ? '/admin/pi-models?make=' + encodeURIComponent(make) : '/admin/pi-models';
  var resp = await fetch(url);
  var data = await resp.json();
  var sel = document.getElementById('rules-canonical');
  if (sel && sel.tagName === 'SELECT') {
    sel.innerHTML = data.models.map(function(m) {
      return '<option value="' + m.replace(/"/g, '&quot;') + '">' + m + '</option>';
    }).join('');
  }
}

function onRulesMakeContextChange(make) {
  var field = document.getElementById('rules-field').value;
  if (field === 'model') {
    loadRulesModelOptions(make);
  }
}
</script>
{% endblock %}
```

- [ ] **Step 2: Verify the rules page renders and the existing test passes**

```
python -m pytest tests/test_admin_api.py::test_rules_page_renders -v
```
Expected: PASS

- [ ] **Step 3: Run full suite one final time**

```
python -m pytest tests/test_admin_api.py -v -k "not integration"
```
Expected: all non-integration tests pass.

- [ ] **Step 4: Commit**

```bash
git add admin_api/templates/rules.html
git commit -m "feat(admin): canonical select with dynamic model fetch on rules page"
```

---

## Self-Review

**Spec coverage:**
- ✓ "Create Rule does nothing" — Task 3 detects HX-Request and returns HTML; Task 4 provides the `<tr>` partial
- ✓ "Can't tell which field isn't mapped" — Task 5 splits fuzzy guess into separate Make Match / Model Match columns with ✓/✗ indicators
- ✓ "High probability of invalid rules" — Task 3 adds backend validation; Tasks 5+6 replace free-text with `<select>` for make/model
- ✓ "NHTSA data in discrepancy workflow" — Task 2 enriches groups; Task 5 adds the column and "Use NHTSA" prefill buttons
- ✓ `GET /admin/pi-models` endpoint — Task 1 implements and tests it
- ✓ Trim field kept as free text — not in PI, handled as `<input>` fallback in both templates

**Placeholder scan:** No TBDs or "implement later" found.

**Type consistency:** `rule` dict keys from `_rule_to_dict` are used consistently in `_rule_row.html` and the HTMX success response. The loop variable in `rules.html` was renamed from `r` to `rule` to match the partial. `get_pi_models_filtered` signature is `(make: str | None, pi_engine: Engine | None) -> list[str]` consistently across discrepancies.py, rules.py import, and tests.
