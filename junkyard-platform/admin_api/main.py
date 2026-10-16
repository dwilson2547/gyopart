"""Junkyard admin: the JSON API (admin_api/api) behind the admin SPA (admin_ui/, served from STATIC_DIR), with
authentik sign-in in front (admin_api/auth). Design: docs/admin-rewrite-design.md.

    JUNKYARD_DATABASE_URL=... PARTS_DATABASE_URL=... uvicorn admin_api.main:app --port 8300

The schema belongs to Alembic (db/); the app never creates tables. Engines connect lazily, so the app starts
(and answers 503 on data routes) while a database is down.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from admin_api.api import router as api_router
from admin_api.auth.web import install as install_auth

_engine: Engine | None = None
_pi_engine: Engine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _pi_engine
    _engine = create_engine(os.environ["JUNKYARD_DATABASE_URL"], pool_pre_ping=True,
                            connect_args={"options": "-c statement_timeout=10000"})
    if parts_url := os.environ.get("PARTS_DATABASE_URL"):
        _pi_engine = create_engine(parts_url, pool_pre_ping=True)
    yield
    _engine.dispose()
    if _pi_engine:
        _pi_engine.dispose()


app = FastAPI(title="Junkyard Admin", lifespan=lifespan)


@app.exception_handler(OperationalError)
async def _db_unreachable(request: Request, exc: OperationalError):
    # A dropped/unreachable database is the common failure; say so instead of a bare 500.
    return JSONResponse({"detail": "database unreachable; try again shortly"}, status_code=503)


# authentik sign-in + the guard in front of everything (on when OIDC_ISSUER is set).
install_auth(app)
app.include_router(api_router)


@app.get("/admin/{rest:path}", include_in_schema=False)
async def old_pages(rest: str):
    """The Jinja pages (/admin/ui/...) were replaced by the SPA; old bookmarks land on it."""
    return RedirectResponse("/")


_static = Path(os.environ["STATIC_DIR"]) if os.environ.get("STATIC_DIR") else None
if _static and _static.is_dir():
    if (_static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (_static / path).resolve()
        if path and file.is_file() and _static.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(_static / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {"detail": "admin API; the UI is built into STATIC_DIR (or run admin_ui with `npm run dev`)"}
