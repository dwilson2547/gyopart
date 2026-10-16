"""The discrepancy-fix MCP endpoint and the OAuth that signs its clients in (docs/admin-rewrite-design.md §2.7).

`install(app)` adds, when PUBLIC_URL is https (or localhost) and sign-in is on:
  /mcp                                    the MCP server (bearer tokens only)
  /.well-known/oauth-*, /authorize, /token, /register, /revoke   the SDK's OAuth handlers
  /oauth/consent                          approve a client (needs the admin session)
  /api/agents                             connected clients, for the SPA's Agents list (session, like all /api)
The auth guard (auth/web.py) lets the OAuth and MCP paths through; they authenticate themselves.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from sqlalchemy import delete, select
from starlette.routing import Route

log = logging.getLogger("admin_api.mcp")

# Paths the auth guard must not touch: the protocol handlers and the MCP endpoint check their own credentials.
OPEN_PATHS = ("/mcp", "/authorize", "/token", "/register", "/revoke")
OPEN_PREFIXES = ("/.well-known/oauth-",)
CONSENT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; "
               "frame-ancestors 'none'")


def is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


class _Issuer(BaseModel):
    # RFC 8414 clients compare the issuer exactly; keep it free of a trailing slash.
    model_config = ConfigDict(url_preserve_empty_path=True)
    u: AnyHttpUrl


def install(app: FastAPI, env: dict | None = None):
    """Returns the MCP server (its session manager must run in the app's lifespan), or None when off."""
    env = env if env is not None else dict(os.environ)
    public_url = env.get("PUBLIC_URL", "").rstrip("/")
    host = urlsplit(public_url).hostname
    if not env.get("OIDC_ISSUER") or not (public_url.startswith("https://") or host in ("localhost", "127.0.0.1")):
        log.warning("MCP off: needs sign-in (OIDC_ISSUER) and an https PUBLIC_URL")
        return None

    from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions

    from ..api.common import engines
    from ..auth.web import LOGIN, current_user
    from . import oauth, server as mcp_server
    from .store import grants

    def engine():
        return engines()[0]

    mcp, mcp_app = mcp_server.build(public_url)

    def consent_page(body: str, status: int = 200, redirect_to: str | None = None) -> HTMLResponse:
        csp = CONSENT_CSP
        if redirect_to:
            csp = csp.replace("form-action 'self'", f"form-action 'self' {oauth.form_action_source(redirect_to)}")
        return HTMLResponse(body, status_code=status, headers={
            "Content-Security-Policy": csp, "Cache-Control": "no-store", "X-Frame-Options": "DENY"})

    @app.get(oauth.CONSENT_PATH, include_in_schema=False)
    def consent(request: Request, req: str = ""):
        user = current_user(request)
        if user is None:
            back = f"{oauth.CONSENT_PATH}?req={quote(req, safe='')}"
            return RedirectResponse(f"{LOGIN}?next={quote(back, safe='')}", 302)
        with engine().begin() as conn:
            try:
                row, info = oauth.pending(conn, req)
                nonce = oauth.show(conn, row, user)
            except oauth.ConsentError as exc:
                return consent_page(oauth.error_html(str(exc)), 400)
        return consent_page(oauth.consent_html(info, row["params"], user, req, nonce),
                            redirect_to=row["params"]["redirect_uri"])

    @app.post(oauth.CONSENT_PATH, include_in_schema=False)
    async def consent_decide(request: Request):
        form = await request.form()
        req, nonce = str(form.get("req") or ""), str(form.get("nonce") or "")
        approve = form.get("decision") == "allow"
        user = current_user(request)
        with engine().begin() as conn:
            try:
                if user is None:
                    raise oauth.ConsentError("You are no longer signed in. Start the connection again.")
                row, _ = oauth.pending(conn, req)
                url = oauth.decide(conn, row, user, nonce, approve)
            except oauth.ConsentError as exc:
                return consent_page(oauth.error_html(str(exc)), 400)
        return RedirectResponse(url, status_code=303)

    @app.get("/api/agents", include_in_schema=False)
    def list_agents(request: Request):
        user = current_user(request)
        with engine().connect() as conn:
            rows = conn.execute(select(grants).where(grants.c.user_sub == user["sub"])
                                .order_by(grants.c.created_at.desc())).mappings().all()
        return {"agents": [oauth.grant_out(g) for g in rows], "mcpUrl": public_url + "/mcp"}

    @app.delete("/api/agents/{grant_id}", include_in_schema=False)
    def revoke_agent(grant_id: str, request: Request):
        user = current_user(request)
        with engine().begin() as conn:
            n = conn.execute(delete(grants).where(grants.c.id == grant_id,
                                                  grants.c.user_sub == user["sub"])).rowcount
        if not n:
            raise HTTPException(404, "no such agent")
        return {"revoked": grant_id}

    issuer = _Issuer(u=public_url).u
    app.router.routes.extend(create_auth_routes(
        oauth.Provider(engine, public_url), issuer_url=issuer,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[oauth.SCOPE], default_scopes=[oauth.SCOPE]),
        revocation_options=RevocationOptions(enabled=True)))
    resource_routes = create_protected_resource_routes(
        resource_url=AnyHttpUrl(public_url + "/mcp"), authorization_servers=[issuer],
        scopes_supported=[oauth.SCOPE], resource_name="junkyard admin")
    app.router.routes.extend(resource_routes)
    # Some clients look for the metadata without the resource path.
    app.router.routes.append(Route("/.well-known/oauth-protected-resource", endpoint=resource_routes[0].endpoint,
                                   methods=["GET", "OPTIONS"]))
    app.router.routes.append(Route("/mcp", endpoint=mcp_app, methods=["GET", "POST", "DELETE"]))
    return mcp
