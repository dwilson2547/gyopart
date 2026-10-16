"""OAuth for MCP clients: sign in from the browser, no token to paste.

Copied from webdoc (apps/webdoc/api/webdoc/oauth.py, itself from nodewright), on the admin's database and its
cookie session instead of a user table.

The admin is the authorization server its MCP clients talk to. The SDK's handlers (mcp.server.auth) do the
protocol: metadata, dynamic client registration, /authorize parameter checks, PKCE, /token, /revoke. This module
is the storage behind them and the one decision they leave to the app: the consent page, where the signed-in
user approves a client. Who the user is still comes from authentik, through the admin's normal sign-in, so only
members of the authentik group that guards the admin can approve one.

Clients register themselves without any credentials, so anyone can create one with any name. The consent page
therefore shows where the user will be sent back to, and approving needs the user's own session plus a one-time
nonce that only the rendered page carries.
"""
from __future__ import annotations

import hashlib
import html
import secrets
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Callable
from urllib.parse import urlencode, urlsplit

import anyio
from pydantic import AnyUrl
from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection, Engine

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, RegistrationError, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .store import clients, codes, grants, new_id, requests, utcnow

SCOPE = "fixes"
ACCESS_PREFIX = "gya_"
REFRESH_PREFIX = "gyr_"
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=5)
REQUEST_TTL = timedelta(minutes=10)
UNUSED_CLIENT_TTL = timedelta(days=1)
CONSENT_PATH = "/oauth/consent"
MAX_GRANTS_PER_USER = 20
TOUCH_EVERY = timedelta(minutes=1)
LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}
AGENT_PREFIX = "agent:"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def redirect_ok(uri: str) -> bool:
    """https anywhere, http only to this machine (CLI clients listen on a loopback port), or an app's own scheme
    (vscode://, cursor://)."""
    parts = urlsplit(uri)
    if parts.fragment:
        return False
    if parts.scheme == "https":
        return bool(parts.hostname)
    if parts.scheme == "http":
        return parts.hostname in LOOPBACK or f"[{parts.hostname}]" in LOOPBACK
    return parts.scheme not in ("", "javascript", "data", "file", "blob", "about")


def form_action_source(uri: str) -> str:
    """The CSP source that lets the consent form's redirect reach `uri`; browsers apply form-action to the
    redirect after a form POST."""
    parts = urlsplit(uri)
    if parts.scheme in ("http", "https"):
        return f"{parts.scheme}://{parts.netloc}"
    return f"{parts.scheme}:"


def client_label(info: dict) -> str:
    return " ".join(str(info.get("client_name") or "MCP client").split())[:100]


def user_label(user: dict) -> str:
    return str(user.get("email") or user.get("name") or user.get("sub") or "user")


@dataclass
class Principal:
    """Who an MCP request acts for."""
    grant_id: str
    user: dict
    client_name: str

    @property
    def created_by(self) -> str:
        """What mappings and rules record as their creator (both columns are 100 characters)."""
        return f"{AGENT_PREFIX}{self.client_name} ({user_label(self.user)})"[:100]


def principal(conn: Connection, raw: str) -> Principal | None:
    """The grant behind a bearer access token, if it is current; marks it used (at most once a minute)."""
    if not raw.startswith(ACCESS_PREFIX) or len(raw) > 100:
        return None
    g = conn.execute(select(grants).where(grants.c.access_hash == _hash(raw))).mappings().first()
    if g is None or _aware(g["access_expires_at"]) <= utcnow():
        return None
    now = utcnow()
    if g["last_used_at"] is None or _aware(g["last_used_at"]) < now - TOUCH_EVERY:
        conn.execute(update(grants).where(grants.c.id == g["id"]).values(last_used_at=now))
    return Principal(g["id"], dict(g["user"]), g["client_name"])


def bearer(header: str | None) -> str:
    if not header:
        return ""
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


class Provider:
    """OAuthAuthorizationServerProvider backed by the junkyard database."""

    def __init__(self, engine: Callable[[], Engine], public_url: str):
        self.engine = engine
        self.public_url = public_url.rstrip("/")
        self.resource = self.public_url + "/mcp"

    async def _run(self, fn):
        def go():
            with self.engine().begin() as conn:
                return fn(conn)
        return await anyio.to_thread.run_sync(go)

    # --- clients ----------------------------------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        def go(conn):
            info = conn.execute(select(clients.c.info).where(clients.c.client_id == client_id[:64])).scalar()
            return None if info is None else OAuthClientInformationFull.model_validate(info)
        return await self._run(go)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or len(uris) > 10 or not all(redirect_ok(u) and len(u) <= 500 for u in uris):
            raise RegistrationError("invalid_redirect_uri",
                                    "redirect URIs must be https, http on loopback, or an app scheme")

        def go(conn):
            # Registration is open, so drop clients nobody ever approved.
            conn.execute(delete(clients).where(clients.c.created_at < utcnow() - UNUSED_CLIENT_TTL,
                                               clients.c.client_id.not_in(select(grants.c.client_id))))
            conn.execute(insert(clients).values(client_id=client_info.client_id,
                                                info=client_info.model_dump(mode="json"), created_at=utcnow()))
        await self._run(go)

    # --- authorize: hand over to the consent page ---------------------------------------------------------------

    def resource_ok(self, resource: str | None) -> bool:
        return resource is None or resource.rstrip("/") in (self.public_url, self.resource)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not self.resource_ok(params.resource):
            raise AuthorizeError("invalid_target", "this server only issues tokens for " + self.resource)
        req_id = secrets.token_urlsafe(32)

        def go(conn):
            conn.execute(delete(requests).where(requests.c.expires_at < utcnow()))
            conn.execute(insert(requests).values(id=req_id, client_id=client.client_id,
                                                 params=params.model_dump(mode="json"),
                                                 expires_at=utcnow() + REQUEST_TTL))
        await self._run(go)
        return f"{self.public_url}{CONSENT_PATH}?{urlencode({'req': req_id})}"

    # --- codes ------------------------------------------------------------------------------------------------

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        def go(conn):
            row = conn.execute(select(codes).where(codes.c.code_hash == _hash(authorization_code))).mappings().first()
            if row is None or row["client_id"] != client.client_id:
                return None
            p = row["params"]
            return AuthorizationCode(
                code=authorization_code, scopes=p.get("scopes") or [SCOPE],
                expires_at=_aware(row["expires_at"]).timestamp(), client_id=row["client_id"],
                code_challenge=p["code_challenge"], redirect_uri=AnyUrl(p["redirect_uri"]),
                redirect_uri_provided_explicitly=p["redirect_uri_provided_explicitly"],
                resource=p.get("resource"), subject=row["user"]["sub"])
        return await self._run(go)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        def go(conn):
            h = _hash(authorization_code.code)
            user = conn.execute(select(codes.c.user).where(codes.c.code_hash == h)).scalar()
            # Single use: deleting it is what makes a replayed code fail.
            if user is None or not conn.execute(delete(codes).where(codes.c.code_hash == h)).rowcount:
                raise TokenError("invalid_grant", "authorization code already used")
            old = conn.execute(select(grants.c.id).where(grants.c.user_sub == user["sub"])
                               .order_by(grants.c.created_at)).scalars().all()
            stale = old[:max(0, len(old) - MAX_GRANTS_PER_USER + 1)]
            if stale:
                conn.execute(delete(grants).where(grants.c.id.in_(stale)))
            gid = new_id()
            conn.execute(insert(grants).values(
                id=gid, user_sub=user["sub"], user=user, client_id=client.client_id,
                client_name=client_label(client.model_dump()), scopes=" ".join(authorization_code.scopes),
                resource=authorization_code.resource, created_at=utcnow(),
                **self._placeholder()))
            return self._issue(conn, gid, " ".join(authorization_code.scopes))
        return await self._run(go)

    @staticmethod
    def _placeholder() -> dict:
        # Unique, unguessable values until _issue writes the real hashes in the same transaction.
        now = utcnow()
        return {"access_hash": _hash(secrets.token_hex(16)), "refresh_hash": _hash(secrets.token_hex(16)),
                "access_expires_at": now, "refresh_expires_at": now}

    def _issue(self, conn: Connection, grant_id: str, scopes: str) -> OAuthToken:
        access = ACCESS_PREFIX + secrets.token_urlsafe(32)
        refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
        now = utcnow()
        conn.execute(update(grants).where(grants.c.id == grant_id).values(
            access_hash=_hash(access), refresh_hash=_hash(refresh), scopes=scopes,
            access_expires_at=now + ACCESS_TTL, refresh_expires_at=now + REFRESH_TTL))
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=int(ACCESS_TTL.total_seconds()),
                          refresh_token=refresh, scope=scopes or None)

    # --- refresh ----------------------------------------------------------------------------------------------

    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        def go(conn):
            g = conn.execute(select(grants).where(grants.c.refresh_hash == _hash(refresh_token))).mappings().first()
            if g is None or g["client_id"] != client.client_id:
                return None
            return RefreshToken(token=refresh_token, client_id=g["client_id"], scopes=g["scopes"].split() or [SCOPE],
                                expires_at=int(_aware(g["refresh_expires_at"]).timestamp()),
                                resource=g["resource"], subject=g["user_sub"])
        return await self._run(go)

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        def go(conn):
            g = conn.execute(select(grants.c.id, grants.c.scopes)
                             .where(grants.c.refresh_hash == _hash(refresh_token.token))).first()
            if g is None:
                raise TokenError("invalid_grant", "refresh token is no longer valid")
            return self._issue(conn, g.id, " ".join(scopes) or g.scopes)
        return await self._run(go)

    # --- access tokens ----------------------------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        def go(conn):
            if not token.startswith(ACCESS_PREFIX) or len(token) > 100:
                return None
            g = conn.execute(select(grants).where(grants.c.access_hash == _hash(token))).mappings().first()
            if g is None or _aware(g["access_expires_at"]) <= utcnow():
                return None
            return AccessToken(token=token, client_id=g["client_id"], scopes=g["scopes"].split(),
                               expires_at=int(_aware(g["access_expires_at"]).timestamp()),
                               resource=g["resource"], subject=g["user_sub"])
        return await self._run(go)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        h = _hash(token.token)
        await self._run(lambda conn: conn.execute(
            delete(grants).where((grants.c.access_hash == h) | (grants.c.refresh_hash == h))))

    async def exchange_identity_assertion(self, client, params) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "not supported")


# --- consent page (sync; called from FastAPI routes) -------------------------------------------------------------

class ConsentError(Exception):
    pass


def pending(conn: Connection, req_id: str) -> tuple[dict, dict]:
    row = conn.execute(select(requests).where(requests.c.id == (req_id or "")[:64])).mappings().first()
    if row is None or _aware(row["expires_at"]) <= utcnow():
        raise ConsentError("This sign-in request has expired. Start the connection again from your MCP client.")
    info = conn.execute(select(clients.c.info).where(clients.c.client_id == row["client_id"])).scalar()
    if info is None:
        raise ConsentError("The app that asked to connect is no longer registered.")
    return dict(row), info


def show(conn: Connection, row: dict, user: dict) -> str:
    """Bind the request to the user viewing it; returns the form nonce."""
    if row["user_sub"] and row["user_sub"] != user["sub"]:
        raise ConsentError("This sign-in request belongs to another account.")
    nonce = secrets.token_urlsafe(24)
    conn.execute(update(requests).where(requests.c.id == row["id"]).values(user_sub=user["sub"], nonce=nonce))
    return nonce


def decide(conn: Connection, row: dict, user: dict, nonce: str, approve: bool) -> str:
    """Approve or deny; returns the URL to send the browser back to."""
    if not (row["user_sub"] == user["sub"] and row["nonce"] and nonce
            and secrets.compare_digest(row["nonce"], nonce)):
        raise ConsentError("This approval did not come from the page the admin showed you. Start the connection "
                           "again.")
    p = row["params"]
    conn.execute(delete(requests).where(requests.c.id == row["id"]))
    if not approve:
        return construct_redirect_uri(p["redirect_uri"], error="access_denied",
                                      error_description="the user declined", state=p.get("state"))
    code = secrets.token_urlsafe(32)
    conn.execute(insert(codes).values(code_hash=_hash(code), client_id=row["client_id"],
                                      user={k: user.get(k) for k in ("sub", "name", "email")}, params=p,
                                      expires_at=utcnow() + CODE_TTL))
    return construct_redirect_uri(p["redirect_uri"], code=code, state=p.get("state"))


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · junkyard admin</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;background:#14161b;color:#e4e5e9;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center}}
main{{background:#1c1f26;border:1px solid #2c303a;border-radius:10px;padding:28px 32px;max-width:460px;margin:16px}}
h1{{font-size:19px;margin:0 0 12px}} p{{margin:8px 0}} code{{background:#262a33;padding:1px 5px;
border-radius:4px;word-break:break-all}} .row{{display:flex;gap:10px;margin-top:22px}}
button{{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid #3a3f4b;background:#262a33;color:inherit;
cursor:pointer}} button.primary{{background:#7852ee;border-color:#7852ee;color:#fff}}
.muted{{color:#9096a3;font-size:13px}} a{{color:#a48bf5}}
</style></head><body><main>{body}</main></body></html>"""


def consent_html(info: dict, params: dict, user: dict, req_id: str, nonce: str) -> str:
    e = html.escape
    dest = urlsplit(params["redirect_uri"])
    where = e(dest.netloc or dest.scheme + ":")
    return page("Connect an app", f"""
<h1>Allow <strong>{e(client_label(info))}</strong> to fix discrepancies?</h1>
<p>Signed in as <strong>{e(user_label(user))}</strong>.</p>
<p>It will be able to read discrepancies, vehicles, VIN decodes and the catalogue, and to create decode mappings
and yard rules, ignore discrepancy groups, and delete mappings that agents made. It cannot match vehicles by hand,
trigger scrapes, or delete your own mappings.</p>
<p class="muted">After you answer you will be sent to <code>{where}</code>. Only allow it if you just started
connecting this app yourself; the name above is chosen by the app.</p>
<form method="post" action="{CONSENT_PATH}">
<input type="hidden" name="req" value="{e(req_id)}"><input type="hidden" name="nonce" value="{e(nonce)}">
<div class="row"><button class="primary" name="decision" value="allow" type="submit">Allow</button>
<button name="decision" value="deny" type="submit">Deny</button></div></form>
<p class="muted">You can disconnect it later under <strong>Agents</strong>.</p>""")


def error_html(message: str) -> str:
    return page("Cannot connect", f"<h1>Cannot connect</h1><p>{html.escape(message)}</p>"
                '<p><a href="/">Open the admin</a></p>')


def grant_out(g) -> dict:
    return {"id": g["id"], "clientName": g["client_name"], "user": user_label(g["user"]),
            "createdAt": _aware(g["created_at"]).isoformat(),
            "lastUsedAt": _aware(g["last_used_at"]).isoformat() if g["last_used_at"] else None}
