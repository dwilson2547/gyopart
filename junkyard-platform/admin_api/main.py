from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from junkyard_common.models import Base, Vehicle
from admin_api.discrepancies import VALID_STATUSES, get_grouped_discrepancies, get_pi_makes, get_pi_models_all
from admin_api.discrepancies import router as discrepancies_router
from admin_api.discrepancies import admin_router as discrepancies_admin_router
from admin_api.rules import list_rules
from admin_api.rules import router as rules_router
from admin_api.rules import vehicles_router

_engine: Engine | None = None
_pi_engine: Engine | None = None
_ADMIN_KEY: str | None = None
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _pi_engine
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=10000"},
    )
    Base.metadata.create_all(_engine)
    parts_url = os.environ.get("PARTS_DATABASE_URL")
    if parts_url:
        _pi_engine = create_engine(parts_url, pool_pre_ping=True)
    yield
    _engine.dispose()
    if _pi_engine:
        _pi_engine.dispose()


def _count_affected(engine: Engine, field: str, rule_type: str, raw_value: str) -> int:
    col_map = {"make": Vehicle.make, "model": Vehicle.model, "trim": Vehicle.trim}
    col = col_map.get(field)
    if col is None:
        return 0
    with Session(engine) as session:
        q = select(func.count(Vehicle.id)).where(Vehicle.is_active.is_(True))
        if rule_type == "exact":
            q = q.where(col == raw_value)
        elif rule_type == "prefix":
            q = q.where(col.ilike(raw_value + "%"))
        elif rule_type == "regex":
            q = q.where(col.op("~")(raw_value))
        else:
            return 0
        return session.execute(q).scalar() or 0


app = FastAPI(title="Junkyard Admin API", lifespan=lifespan)

_ui_router = APIRouter(prefix="/admin/ui", tags=["ui"])


@_ui_router.get("/discrepancies", response_class=HTMLResponse, include_in_schema=False)
async def ui_discrepancies(request: Request, status: str = "unresolved"):
    if status not in VALID_STATUSES:
        status = "unresolved"
    groups = get_grouped_discrepancies(_engine, status) if _engine else []
    pi_makes = get_pi_makes(_pi_engine) if _pi_engine else []
    pi_models = get_pi_models_all(_pi_engine) if _pi_engine else []
    return _templates.TemplateResponse(request, "discrepancies.html", {
        "groups": groups, "status": status,
        "active": "discrepancies",
        "pi_makes": pi_makes,
        "pi_models": pi_models,
    })


@_ui_router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
async def ui_rules(request: Request):
    rules = list_rules(_engine) if _engine else []
    pi_makes = get_pi_makes(_pi_engine) if _pi_engine else []
    pi_models = get_pi_models_all(_pi_engine) if _pi_engine else []
    return _templates.TemplateResponse(request, "rules.html", {
        "rules": rules,
        "active": "rules",
        "pi_makes": pi_makes,
        "pi_models": pi_models,
    })


@_ui_router.get("/llm-queue", response_class=HTMLResponse, include_in_schema=False)
async def ui_llm_queue(request: Request):
    pending = list_rules(_engine, include_inactive=True) if _engine else []
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
            "affected_count": _count_affected(
                _engine, r["field"], r["rule_type"], r["raw_value"]
            ) if _engine else 0,
        }
        for r in pending
        if r["created_by"] == "llm_suggested" and not r["is_active"]
    ]
    return _templates.TemplateResponse(request, "llm_queue.html", {
        "suggestions": suggestions,
        "active": "llm_queue",
    })


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/admin/ui/discrepancies?status=unresolved")


app.include_router(discrepancies_router)
app.include_router(discrepancies_admin_router)
app.include_router(rules_router)
app.include_router(vehicles_router)
app.include_router(_ui_router)
