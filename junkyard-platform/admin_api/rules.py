from __future__ import annotations

import datetime
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import escape
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from admin_api.discrepancies import _get_pi_engine, get_pi_makes, get_pi_models_all, get_pi_models_filtered
from junkyard_common.models import MappingDiscrepancy, MappingRule, Vehicle
from admin_api.models import CreateRuleRequest, ManualOverrideRequest

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

router = APIRouter(prefix="/admin/rules", tags=["rules"])
vehicles_router = APIRouter(prefix="/admin/vehicles", tags=["vehicles"])


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
        session.refresh(rule)
        return _rule_to_dict(rule)


def get_rule_by_id(engine: Engine, rule_id: int) -> dict | None:
    with Session(engine) as session:
        rule = session.get(MappingRule, rule_id)
        if rule is None:
            return None
        return _rule_to_dict(rule)


def update_rule(engine: Engine, rule_id: int, req: CreateRuleRequest) -> dict:
    with Session(engine) as session:
        rule = session.get(MappingRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        rule.field = req.field
        rule.rule_type = req.rule_type
        rule.raw_value = req.raw_value
        rule.canonical_value = req.canonical_value
        rule.make_context = req.make_context
        rule.scope = req.scope
        rule.priority = req.priority
        session.commit()
        session.refresh(rule)
        return _rule_to_dict(rule)


def deactivate_rule(engine: Engine, rule_id: int) -> dict:
    with Session(engine) as session:
        rule = session.get(MappingRule, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="rule not found")
        rule.is_active = False
        session.commit()
        return _rule_to_dict(rule)


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


def run_reprocess() -> None:
    from pipeline.reprocess_job import run_reprocess as _run
    _run(dry_run=False)


def _get_engine() -> Engine:
    from admin_api.main import _engine
    if _engine is None:
        raise HTTPException(status_code=503, detail="service not ready")
    return _engine


# ── Rule routes ────────────────────────────────────────────────────────────

class _ApproveRequest(BaseModel):
    approved_by: str = "admin"


@router.get("")
def get_rules(include_inactive: bool = False, engine: Engine = Depends(_get_engine)):
    return {"rules": list_rules(engine, include_inactive)}


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
            valid = (
                get_pi_models_filtered(req.make_context, pi_engine)
                if req.make_context
                else get_pi_models_all(pi_engine)
            )
            if req.canonical_value not in valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown model: {req.canonical_value!r}.",
                )

    rule = create_rule(engine, req)

    if request.headers.get("HX-Request"):
        hx_target = request.headers.get("HX-Target", "")
        if hx_target == "rules-tbody":
            return _templates.TemplateResponse(request, "_rule_row.html", {"rule": rule})
        # Discrepancy form — return inline success row
        return HTMLResponse(
            f'<tr id="rule-form-{escape(hx_target.replace("rule-form-", ""))}" style="display:none">'
            f'<td colspan="9"><span style="color:#28a745;font-size:0.85rem">'
            f'✓ Rule saved: <code>{escape(rule["raw_value"])}</code>'
            f' → <code>{escape(rule["canonical_value"])}</code>'
            f'</span></td></tr>'
        )

    return rule


@router.get("/{rule_id}/edit")
def get_rule_edit(
    request: Request,
    rule_id: int,
    engine: Engine = Depends(_get_engine),
    pi_engine: Engine | None = Depends(_get_pi_engine),
):
    rule = get_rule_by_id(engine, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    pi_makes = get_pi_makes(pi_engine) if pi_engine else []
    return _templates.TemplateResponse(
        request, "_rule_edit_row.html", {"rule": rule, "pi_makes": pi_makes}
    )


@router.get("/{rule_id}")
def get_rule(
    request: Request,
    rule_id: int,
    engine: Engine = Depends(_get_engine),
    pi_engine: Engine | None = Depends(_get_pi_engine),
):
    rule = get_rule_by_id(engine, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    pi_makes = get_pi_makes(pi_engine) if pi_engine else []
    return _templates.TemplateResponse(
        request, "_rule_row.html", {"rule": rule, "pi_makes": pi_makes}
    )


@router.patch("/{rule_id}")
def patch_rule(
    request: Request,
    rule_id: int,
    field: str = Form(...),
    rule_type: str = Form(...),
    raw_value: str = Form(...),
    canonical_value: str = Form(...),
    scope: str = Form("global"),
    make_context: str | None = Form(None),
    priority: int = Form(100),
    engine: Engine = Depends(_get_engine),
    pi_engine: Engine | None = Depends(_get_pi_engine),
):
    try:
        req = CreateRuleRequest(
            field=field, rule_type=rule_type, raw_value=raw_value,
            canonical_value=canonical_value, scope=scope,
            make_context=make_context, priority=priority,
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
            valid = (
                get_pi_models_filtered(req.make_context, pi_engine)
                if req.make_context
                else get_pi_models_all(pi_engine)
            )
            if req.canonical_value not in valid:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown model: {req.canonical_value!r}.",
                )

    rule = update_rule(engine, rule_id, req)
    pi_makes = get_pi_makes(pi_engine) if pi_engine else []
    if request.headers.get("HX-Request"):
        return _templates.TemplateResponse(
            request, "_rule_row.html", {"rule": rule, "pi_makes": pi_makes}
        )
    return rule


@router.post("/{rule_id}/approve")
def post_approve_rule(
    rule_id: int,
    body: _ApproveRequest,
    background_tasks: BackgroundTasks,
    engine: Engine = Depends(_get_engine),
):
    result = approve_rule(engine, rule_id, body.approved_by)
    background_tasks.add_task(run_reprocess)
    return result


@router.post("/{rule_id}/deactivate")
def post_deactivate_rule(request: Request, rule_id: int, engine: Engine = Depends(_get_engine)):
    result = deactivate_rule(engine, rule_id)
    if request.headers.get("HX-Request"):
        return Response(content="", status_code=200)
    return result


# ── Vehicle override routes ────────────────────────────────────────────────


@vehicles_router.patch("/{vehicle_id}/car-id")
def patch_vehicle_car_id(
    vehicle_id: int,
    body: ManualOverrideRequest,
    engine: Engine = Depends(_get_engine),
):
    return apply_manual_override(engine, vehicle_id, body.car_id)
