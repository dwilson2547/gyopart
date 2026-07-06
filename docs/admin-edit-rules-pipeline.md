# Admin: Edit Rules + Manual Pipeline Trigger

**Date:** 2026-05-24  
**Status:** Approved

## Problem

The admin UI has no way to correct a rule once created (only deactivate + recreate), and no way to trigger the mapping pipeline from the UI. Rules typically need to be created in pairs (make + model) before the pipeline is useful to run, so triggering on save would be premature.

## Features

### 1 — Inline Rule Editing

An "Edit" button on each rule row swaps the row for an editable form. Save applies the change; Cancel restores the original row. `applied_count` is preserved (historical records were mapped by the previous version of the rule, so the count remains meaningful).

**Backend — routes added to `rules.py`:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/rules/{id}` | Return display row HTML (`_rule_row.html`) |
| `GET` | `/admin/rules/{id}/edit` | Return edit form row HTML (`_rule_edit_row.html`) |
| `PATCH` | `/admin/rules/{id}` | Update rule, return display row HTML |

`update_rule(engine, rule_id, req: CreateRuleRequest)` reuses the existing model. Canonical value validation (PI make/model check) mirrors `post_rule`. `applied_count`, `created_by`, `created_at`, `llm_*`, and `approved_*` fields are left untouched.

**Frontend:**

- `_rule_row.html`: Add "Edit" button → `hx-get="/admin/rules/{id}/edit" hx-target="#rule-{id}" hx-swap="outerHTML"`
- New `_rule_edit_row.html`: Colspan-9 edit form with all editable fields pre-filled. Canonical value select uses the same make/model/trim dynamic pattern (pi_makes passed from server; model options loaded via `/admin/pi-models`). Cancel → `hx-get="/admin/rules/{id}" hx-target="#rule-{id}" hx-swap="outerHTML"`. Save → `hx-patch="/admin/rules/{id}"`.
- `GET /admin/rules/{id}` also needs `pi_makes` in context so the edit route round-trip is self-contained.
- `_rule_edit_row.html` includes an IIFE `<script>` for field-change handling scoped by rule id (avoids global namespace conflicts if two rows ever enter edit simultaneously — unlikely but safe).

### 2 — Manual Pipeline Trigger

A "Run Pipeline" button in the discrepancy page header area. Clicking it fires the reprocess in the background and shows an inline status message. The user creates all needed rules first, then triggers once.

**Backend — new route in `discrepancies.py` (on `admin_router`):**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/reprocess` | Fire `run_reprocess` as background task, return status HTML |

Returns `HTMLResponse` with a short confirmation string (e.g. "Reprocessing started — refresh in a moment") that HTMX swaps into a status span next to the button.

**Frontend (`discrepancies.html`):**

```html
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem">
  <div class="tabs">…</div>
  <div style="display:flex; align-items:center; gap:0.5rem">
    <button hx-post="/admin/reprocess" hx-target="#pipeline-status" hx-swap="innerHTML"
            class="btn btn-primary">Run Pipeline</button>
    <span id="pipeline-status" style="font-size:0.85rem;color:#6c757d"></span>
  </div>
</div>
```

## Files Changed

| File | Change |
|------|--------|
| `admin_api/rules.py` | Add `update_rule`, `GET /{id}`, `GET /{id}/edit`, `PATCH /{id}` |
| `admin_api/discrepancies.py` | Add `POST /admin/reprocess` on `admin_router` |
| `admin_api/templates/_rule_row.html` | Add Edit button |
| `admin_api/templates/_rule_edit_row.html` | New — edit form row |
| `admin_api/templates/discrepancies.html` | Add Run Pipeline button + status span |
| `tests/test_admin_api.py` | Tests for edit routes and reprocess endpoint |

## Out of Scope

- Pre-flight record count ("how many records will this rule touch") — stretch goal
- Auto-trigger pipeline on rule save
- Edit form on the discrepancy page inline forms (create-only)
- Editing `source` / `location_id` fields (low value, keep simple)
