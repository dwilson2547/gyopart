"""Sign-in through authentik: OIDC authorization code flow with PKCE (admin-rewrite-design phase 4).
Ported from the scrape-job-manager UI (web-scrapers/scrape-job-manager/ui/backend/sjm_ui/oidc.py), fixes
included: the issuer is checked as the discovery document gives it (authentik keeps the trailing slash), and
the JWKS fetch sends a named User-Agent (Cloudflare 403s urllib's default). No user table: the verified
claims become the session cookie. Who may sign in is the authentik group binding (gyopart-admin).

State, nonce, the PKCE verifier and the page to return to ride in a short-lived HttpOnly cookie scoped to
the callback path.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
from urllib.parse import urlencode

import httpx
import jwt

log = logging.getLogger("admin_api.oidc")

FLOW_COOKIE = "gya_oidc"
FLOW_PATH = "/api/auth/oidc"
FLOW_TTL_S = 600
USER_AGENT = "gyopart-admin"


class SignInRefused(Exception):
    pass


class Provider:
    """authentik's endpoints and signing keys, fetched on first use."""

    def __init__(self, issuer: str, client_id: str, client_secret: str):
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._meta: dict | None = None
        self._jwks: jwt.PyJWKClient | None = None
        self._lock = threading.Lock()

    def metadata(self) -> dict:
        with self._lock:
            if self._meta is None:
                url = self.issuer + "/.well-known/openid-configuration"
                r = httpx.get(url, timeout=10)
                r.raise_for_status()
                self._meta = r.json()
                # Named User-Agent: PyJWKClient fetches with urllib, and Cloudflare
                # (in front of auth.danwils.com) 403s the default Python-urllib one.
                self._jwks = jwt.PyJWKClient(self._meta["jwks_uri"], cache_keys=True,
                                             headers={"User-Agent": USER_AGENT})
            return self._meta

    def exchange(self, code: str, verifier: str, redirect_uri: str) -> dict:
        r = httpx.post(self.metadata()["token_endpoint"], timeout=15,
                       auth=(self.client_id, self.client_secret),
                       data={"grant_type": "authorization_code", "code": code,
                             "redirect_uri": redirect_uri, "code_verifier": verifier})
        if r.status_code != 200:
            log.warning("oidc: token endpoint %s: %s", r.status_code, r.text[:300])
            raise SignInRefused("authentik refused the sign-in code")
        return r.json()

    def verify(self, id_token: str, nonce: str) -> dict:
        try:
            self.metadata()
            key = self._jwks.get_signing_key_from_jwt(id_token).key
            claims = jwt.decode(
                id_token, key, algorithms=["RS256", "ES256"],
                # authentik's issuer keeps its trailing slash: compare against
                # the discovery document's, not the configured URL trimmed.
                audience=self.client_id, issuer=self._meta["issuer"],
                options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            log.warning("oidc: ID token rejected: %s", exc)
            raise SignInRefused("the sign-in could not be verified") from None
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise SignInRefused("the sign-in could not be verified")
        return claims


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> str:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode()


def local_path(path: str | None) -> str:
    """`path` if it is a path on this site, else "/": the return-to page must
    never send a fresh sign-in off to another origin."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path


def flow_next(flow_cookie: str | None) -> str:
    """The return-to page recorded in a flow cookie ("/" if there's none or it's unreadable)."""
    parts = (flow_cookie or "").split(".")
    try:
        return local_path(_unb64(parts[3])) if len(parts) == 4 else "/"
    except ValueError:
        return "/"


def redirect_uri(public_url: str) -> str:
    return f"{public_url.rstrip('/')}{FLOW_PATH}/callback"


def begin(provider: Provider, public_url: str, next_path: str = "/") -> tuple[str, str]:
    """Return (authorization URL, flow cookie value)."""
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    url = provider.metadata()["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": provider.client_id,
        "redirect_uri": redirect_uri(public_url), "scope": "openid email profile",
        "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return url, f"{state}.{nonce}.{verifier}.{_b64(local_path(next_path).encode())}"


def finish(provider: Provider, public_url: str, flow_cookie: str, code: str, state: str) -> tuple[dict, str]:
    """Return (session user, local path to land on)."""
    parts = (flow_cookie or "").split(".")
    if len(parts) != 4 or not state or not secrets.compare_digest(parts[0], state):
        raise SignInRefused("the sign-in expired or came from another window")
    _, nonce, verifier, next_b64 = parts
    try:
        next_path = local_path(_unb64(next_b64))
    except ValueError:
        next_path = "/"
    tokens = provider.exchange(code, verifier, redirect_uri(public_url))
    claims = provider.verify(tokens.get("id_token") or "", nonce)
    user = {"sub": claims["sub"], "name": claims.get("name") or claims.get("preferred_username") or claims["sub"],
            "email": claims.get("email")}
    return user, next_path
