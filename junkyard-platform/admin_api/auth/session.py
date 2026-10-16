"""Signed-cookie sessions: payload + HMAC-SHA256, no server-side state. The
signing key is the OIDC client secret, so rotating it invalidates sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

COOKIE = "gya_session"
TTL_S = 12 * 3600


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(secret: str, user: dict) -> str:
    payload = _b64(json.dumps({**user, "exp": int(time.time()) + TTL_S}).encode())
    sig = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify(secret: str, cookie: str | None) -> dict | None:
    if not cookie or "." not in cookie:
        return None
    payload, sig = cookie.rsplit(".", 1)
    want = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return None
    try:
        user = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(user.get("exp"), int) or user["exp"] < time.time():
        return None
    return user
