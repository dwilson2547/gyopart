"""Sign-in routes and the guard in front of everything (the SPA and its /api).

Off unless OIDC_ISSUER is set (local dev, tests). With it on:
  - a signed-out page load (any GET outside /api) goes to authentik and comes back to the same page;
  - a signed-out API call or write gets 401 (the SPA then sends the browser to sign in);
  - every write needs the X-Admin header (the SPA sends it): a custom header a cross-site form can't add,
    so a signed-in browser can't be made to write by another site.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from urllib.parse import quote, urlsplit

from . import session

LOGIN = "/api/auth/oidc/login"
PUBLIC = {"/api/config", LOGIN, "/api/auth/oidc/callback", "/favicon.svg"}
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


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
        return {"app": "junkyard-admin", "phase": 4, "oidc": bool(issuer)}

    @app.get("/api/me", include_in_schema=False)
    def me(request: Request):
        return {"user": current_user(request), "oidc": bool(issuer)}

    if not issuer:
        return False

    from .oidc import FLOW_COOKIE, FLOW_PATH, FLOW_TTL_S, Provider, SignInRefused, begin, finish

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
        if error:
            return JSONResponse({"detail": f"authentik: {error}"}, status_code=401)
        try:
            user, next_path = finish(provider, public_url, request.cookies.get(FLOW_COOKIE), code, state)
        except SignInRefused as exc:
            return JSONResponse({"detail": str(exc)}, status_code=401)
        r = RedirectResponse(next_path)
        r.set_cookie(session.COOKIE, session.sign(secret, user), max_age=session.TTL_S, httponly=True,
                     samesite="lax", secure=secure)
        r.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
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
                and not path.startswith("/api/") and not path.startswith("/assets/"):
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(public_url.rstrip("/") + target)
        request.state.user = session.verify(secret, request.cookies.get(session.COOKIE))
        if path in PUBLIC or path.startswith("/assets/"):
            return await call_next(request)
        if request.state.user is None:
            if request.method == "GET" and not path.startswith("/api/") and path != "/api":
                target = path + (f"?{request.url.query}" if request.url.query else "")
                return RedirectResponse(f"{LOGIN}?next={quote(target, safe='')}")
            if path != "/api/me":
                return JSONResponse({"detail": "sign-in required"}, status_code=401)
        if request.method in WRITES and request.headers.get("X-Admin") != "1":
            return JSONResponse({"detail": "missing X-Admin header"}, status_code=403)
        return await call_next(request)

    return True
