"""Sign-in routes and the guard in front of everything (the SPA and its /api).

Off unless OIDC_ISSUER is set (local dev, tests). With it on:
  - a signed-out page load (a top-level navigation outside /api) goes to authentik and comes back to the same
    page; background requests (favicon, images, scripts) just get 401, so they never start a sign-in that would
    overwrite the one in progress;
  - a failed callback (e.g. a duplicate request re-using a spent code) quietly restarts the sign-in once; the
    authentik session is usually still alive, so the retry is instant;
  - a signed-out API call or write gets 401 (the SPA then sends the browser to sign in);
  - every write needs the X-Admin header (the SPA sends it): a custom header a cross-site form can't add,
    so a signed-in browser can't be made to write by another site.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from urllib.parse import quote, urlsplit

from ..mcp import is_open
from . import session

CONSENT_PATH = "/oauth/consent"   # admin_api/mcp/oauth.py

LOGIN = "/api/auth/oidc/login"
RETRY_COOKIE = "gya_retry"   # marks one automatic sign-in retry after a failed callback
PUBLIC = {"/api/config", LOGIN, "/api/auth/oidc/callback", "/favicon.svg"}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def is_navigation(request: Request) -> bool:
    """A top-level page load (the browser says so; older clients: they ask for HTML)."""
    mode = request.headers.get("sec-fetch-mode")
    if mode is not None:
        return mode == "navigate"
    return "text/html" in request.headers.get("accept", "")


def _failed_page(next_path: str, reason: str) -> HTMLResponse:
    retry = f"{LOGIN}?next={quote(next_path, safe='')}"
    body = (f"<!doctype html><meta charset=utf-8><title>Sign-in didn't complete</title>"
            f"<body style='font:15px system-ui;background:#14161b;color:#e4e5e9;padding:40px'>"
            f"<h2>Sign-in didn't complete</h2><p style='color:#9096a3'>{reason}</p>"
            f"<p><a style='color:#7852ee' href='{retry}'>Try again</a></p>")
    return HTMLResponse(body, status_code=401)


def current_user(request: Request) -> dict | None:
    return getattr(request.state, "user", None)


def who(request: Request) -> str:
    """For created_by columns: the signed-in user's email (or name), else "admin" (auth off)."""
    user = current_user(request)
    return (user.get("email") or user.get("name") or user.get("sub")) if user else "admin"


def install(app: FastAPI, env: dict | None = None) -> bool:
    """Add the sign-in routes and the guard when OIDC_ISSUER is configured. Returns whether auth is on."""
    env = env if env is not None else dict(os.environ)
    issuer = env.get("OIDC_ISSUER", "")

    @app.get("/api/config", include_in_schema=False)
    def config():
        return {"app": "junkyard-admin", "oidc": bool(issuer)}

    @app.get("/api/me", include_in_schema=False)
    def me(request: Request):
        return {"user": current_user(request), "oidc": bool(issuer)}

    if not issuer:
        return False

    from .oidc import FLOW_COOKIE, FLOW_PATH, FLOW_TTL_S, Provider, SignInRefused, begin, finish, flow_next

    secret = env["OIDC_CLIENT_SECRET"]
    provider = Provider(issuer, env["OIDC_CLIENT_ID"], secret)
    public_url = env.get("PUBLIC_URL", "")
    secure = public_url.startswith("https://")
    public_host = urlsplit(public_url).netloc

    @app.get(FLOW_PATH + "/login", include_in_schema=False)
    def oidc_login(next: str = "/"):
        url, flow = begin(provider, public_url, next)
        r = RedirectResponse(url)
        r.set_cookie(FLOW_COOKIE, flow, max_age=FLOW_TTL_S, httponly=True, samesite="lax", secure=secure,
                     path=FLOW_PATH)
        return r

    @app.get(FLOW_PATH + "/callback", include_in_schema=False)
    def oidc_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        flow = request.cookies.get(FLOW_COOKIE)
        next_path = flow_next(flow)
        try:
            if error:
                raise SignInRefused(f"authentik said: {error}")
            user, next_path = finish(provider, public_url, flow, code, state)
        except SignInRefused as exc:
            if session.verify(secret, request.cookies.get(session.COOKIE)):
                return RedirectResponse(next_path)       # a duplicate after a sign-in that already worked
            if not request.cookies.get(RETRY_COOKIE):     # one quiet retry, then say so
                r = RedirectResponse(f"{LOGIN}?next={quote(next_path, safe='')}")
                r.set_cookie(RETRY_COOKIE, "1", max_age=120, httponly=True, samesite="lax", secure=secure,
                             path=FLOW_PATH)
                return r
            r = _failed_page(next_path, str(exc))
            r.delete_cookie(RETRY_COOKIE, path=FLOW_PATH)
            return r
        r = RedirectResponse(next_path)
        r.set_cookie(session.COOKIE, session.sign(secret, user), max_age=session.TTL_S, httponly=True,
                     samesite="lax", secure=secure)
        r.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
        r.delete_cookie(RETRY_COOKIE, path=FLOW_PATH)
        return r

    @app.post("/api/auth/logout", include_in_schema=False)
    def logout():
        r = JSONResponse({"ok": True})
        r.delete_cookie(session.COOKIE)
        return r

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        # The session cookie belongs to the public host: send page loads on any other host (the LAN ingress)
        # there, or they'd loop through sign-in forever.
        if public_host and request.headers.get("host") != public_host and request.method == "GET" \
                and not path.startswith("/api/") and not path.startswith("/assets/") and not is_open(path):
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(public_url.rstrip("/") + target)
        request.state.user = session.verify(secret, request.cookies.get(session.COOKIE))
        # The MCP endpoint and OAuth handlers check their own credentials; the consent page checks the session
        # itself (its form post is bound to the page by a nonce, so it needs no X-Admin header).
        if path in PUBLIC or path.startswith("/assets/") or is_open(path) or path == CONSENT_PATH:
            return await call_next(request)
        if request.state.user is None:
            if request.method == "GET" and not path.startswith("/api/") and is_navigation(request):
                target = path + (f"?{request.url.query}" if request.url.query else "")
                return RedirectResponse(f"{LOGIN}?next={quote(target, safe='')}")
            if path != "/api/me":
                return JSONResponse({"detail": "sign-in required"}, status_code=401)
        if request.method in WRITES and request.headers.get("X-Admin") != "1":
            return JSONResponse({"detail": "missing X-Admin header"}, status_code=403)
        return await call_next(request)

    return True
