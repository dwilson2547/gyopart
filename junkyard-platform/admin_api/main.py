from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from junkyard_common.models import Base
from admin_api.discrepancies import VALID_STATUSES, get_grouped_discrepancies
from admin_api.discrepancies import router as discrepancies_router
from admin_api.rules import list_rules
from admin_api.rules import router as rules_router
from admin_api.rules import vehicles_router

_engine: Engine | None = None
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    url = os.environ["JUNKYARD_DATABASE_URL"]
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=10000"},
    )
    Base.metadata.create_all(_engine)
    yield
    _engine.dispose()


app = FastAPI(title="Junkyard Admin API", lifespan=lifespan)

_ui_router = APIRouter(prefix="/admin/ui", tags=["ui"])


@_ui_router.get("/discrepancies", response_class=HTMLResponse, include_in_schema=False)
async def ui_discrepancies(request: Request, status: str = "unresolved"):
    if status not in VALID_STATUSES:
        status = "unresolved"
    groups = get_grouped_discrepancies(_engine, status) if _engine else []
    return _templates.TemplateResponse(request, "discrepancies.html", {
        "groups": groups, "status": status,
        "active": "discrepancies",
    })


@_ui_router.get("/rules", response_class=HTMLResponse, include_in_schema=False)
async def ui_rules(request: Request):
    rules = list_rules(_engine) if _engine else []
    return _templates.TemplateResponse(request, "rules.html", {
        "rules": rules,
        "active": "rules",
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
            "affected_count": 0,
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
app.include_router(rules_router)
app.include_router(vehicles_router)
app.include_router(_ui_router)
