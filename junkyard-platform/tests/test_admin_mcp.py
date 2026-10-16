"""Phase 7: the discrepancy-fix MCP (admin_api/mcp). The OAuth flow end to end (register, authorize, consent with the
admin session, token, refresh, revoke), the guard letting the protocol paths through, and tools that run on SQLite
(the catalogue ones). Discrepancy and fix tools use Postgres-only SQL and were verified against the dev DB."""
import base64
import contextlib
import hashlib
import json
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from admin_api.api import router as api_router
from admin_api.auth import session
from admin_api.auth.web import install as install_auth
from admin_api.mcp import install as install_mcp
from admin_api.mcp.oauth import AGENT_PREFIX, Principal
from admin_api.mcp.server import compact_decode
from admin_api.mcp.store import metadata
from tests.test_admin_auth import ENV
from tests.test_car_matcher import _catalogue

BASE = ENV["PUBLIC_URL"]
REDIRECT = "http://127.0.0.1:9999/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
ALICE = {"sub": "alice-sub", "name": "Alice", "email": "alice@example.com"}
CARS = [(1, "2004", "Mercedes-Benz", "C 230", "Base", "1.8L L4 - Gas"),
        (2, "2004", "Mercedes-Benz", "C 320", "Base", "3.2L V6 - Gas"),
        (3, "2005", "Mercedes-Benz", "C 320", "Sport", "3.2L V6 - Gas")]


@pytest.fixture()
def http():
    ji = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(ji)
    holder = {}

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with holder["mcp"].session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    install_auth(app, ENV)
    app.include_router(api_router)
    holder["mcp"] = install_mcp(app, ENV)
    import admin_api.main as m
    with patch.object(m, "_engine", ji), patch.object(m, "_pi_engine", _catalogue(CARS)), \
            TestClient(app, base_url=BASE, follow_redirects=False) as client:
        yield client


def signed_in(http, user=ALICE):
    http.cookies.set(session.COOKIE, session.sign(ENV["OIDC_CLIENT_SECRET"], user))
    return http


def register(http, redirect=REDIRECT, name="Claude Code"):
    return http.post("/register", json={"redirect_uris": [redirect], "client_name": name,
                                        "token_endpoint_auth_method": "none",
                                        "grant_types": ["authorization_code", "refresh_token"],
                                        "response_types": ["code"]})


def authorize(http, client_id):
    r = http.get("/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "code_challenge": CHALLENGE,
        "code_challenge_method": "S256", "state": "st4te", "resource": BASE + "/mcp"})
    assert r.status_code == 302, r.text
    assert r.headers["location"].startswith(BASE + "/oauth/consent?req=")
    return parse_qs(urlsplit(r.headers["location"]).query)["req"][0]


def consent(http, req, decision="allow"):
    page = http.get(f"/oauth/consent?req={req}")
    assert page.status_code == 200, page.text
    nonce = re.search(r'name="nonce" value="([^"]+)"', page.text).group(1)
    return http.post("/oauth/consent", data={"req": req, "nonce": nonce, "decision": decision})


def connect(http):
    client_id = register(http).json()["client_id"]
    req = authorize(http, client_id)
    r = consent(signed_in(http), req)
    assert r.status_code == 303, r.text
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["state"] == ["st4te"]
    tok = http.post("/token", data={"grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": REDIRECT,
                                    "client_id": client_id, "code_verifier": VERIFIER})
    assert tok.status_code == 200, tok.text
    return {**tok.json(), "client_id": client_id, "code": q["code"][0]}


def rpc(http, token, method, params=None):
    return http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                     headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"})


def call(http, token, tool, **args):
    r = rpc(http, token, "tools/call", {"name": tool, "arguments": args})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert not res.get("isError"), res["content"][0]["text"]
    sc = res.get("structuredContent")
    if sc is not None:
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    return json.loads(res["content"][0]["text"])


def test_discovery_without_a_session(http):
    r = http.post("/mcp", json={}, headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401   # from McpAuth, not the admin guard
    assert f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"' in r.headers["www-authenticate"]
    prm = http.get("/.well-known/oauth-protected-resource/mcp").json()
    assert prm["resource"] == BASE + "/mcp"
    assert http.get("/.well-known/oauth-protected-resource").status_code == 200
    meta = http.get("/.well-known/oauth-authorization-server").json()
    assert meta["registration_endpoint"] == BASE + "/register"
    assert meta["code_challenge_methods_supported"] == ["S256"]


def test_registration_rejects_remote_http_redirects(http):
    assert register(http, "http://evil.example/cb").status_code == 400
    assert register(http, "javascript:alert(1)").status_code == 400
    assert register(http, "https://vscode.dev/redirect").status_code == 201


def test_consent_needs_the_admin_session(http):
    req = authorize(http, register(http).json()["client_id"])
    r = http.get(f"/oauth/consent?req={req}", headers={"sec-fetch-mode": "navigate"})
    assert r.status_code in (302, 307) and r.headers["location"].startswith("/api/auth/oidc/login?next=")
    assert "%2Foauth%2Fconsent" in r.headers["location"]
    # A form post without the page's nonce is refused, session or not.
    signed_in(http)
    r = http.post("/oauth/consent", data={"req": req, "nonce": "guess", "decision": "allow"})
    assert r.status_code == 400


def test_full_flow_tools_and_attribution(http):
    tok = connect(http)
    assert tok["access_token"].startswith("gya_") and tok["refresh_token"].startswith("gyr_")
    http.cookies.clear()   # the agent has no browser session; the bearer token is all it sends
    names = {t["name"] for t in rpc(http, tok["access_token"], "tools/list").json()["result"]["tools"]}
    assert {"discrepancy_overview", "list_discrepancy_groups", "get_discrepancy_group", "list_group_vehicles",
            "get_vehicle", "get_vin_decode", "catalogue_cars", "preview_mapping", "create_mapping",
            "create_yard_rule", "set_group_ignored", "delete_mapping"} <= names
    assert not names & {"manual_match", "rescrape"}
    cars = call(http, tok["access_token"], "catalogue_cars", make="mercedes-benz", engine="V6")
    assert cars["total"] == 2 and {c["trim"] for c in cars["cars"]} == {"Base", "Sport"}
    models = call(http, tok["access_token"], "catalogue_models", make="Mercedes-Benz", year_from=2005, year_to=2005)
    assert [(m["name"], m["yearsInRange"]) for m in models] == [("C 320", 1)]
    models = call(http, tok["access_token"], "catalogue_models", make="Mercedes-Benz", year_from=2005, year_to=2005,
                  include_out_of_range=True)
    assert [(m["name"], m["yearsInRange"]) for m in models] == [("C 230", 0), ("C 320", 1)]

    agents = signed_in(http).get("/api/agents").json()
    assert [a["clientName"] for a in agents["agents"]] == ["Claude Code"] and agents["mcpUrl"] == BASE + "/mcp"


def test_code_is_single_use_and_needs_the_verifier(http):
    tok = connect(http)
    again = http.post("/token", data={"grant_type": "authorization_code", "code": tok["code"],
                                      "redirect_uri": REDIRECT, "client_id": tok["client_id"],
                                      "code_verifier": VERIFIER})
    assert again.status_code == 400
    req = authorize(http, tok["client_id"])
    code = parse_qs(urlsplit(consent(http, req).headers["location"]).query)["code"][0]
    bad = http.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                    "client_id": tok["client_id"], "code_verifier": "w" * 64})
    assert bad.status_code == 400


def test_deny_sends_access_denied(http):
    req = authorize(http, register(http).json()["client_id"])
    r = consent(signed_in(http), req, decision="deny")
    assert r.status_code == 303 and "error=access_denied" in r.headers["location"]


def test_refresh_rotates_and_disconnect_revokes(http):
    tok = connect(http)
    r = http.post("/token", data={"grant_type": "refresh_token", "client_id": tok["client_id"],
                                  "refresh_token": tok["refresh_token"]})
    assert r.status_code == 200, r.text
    new = r.json()
    assert rpc(http, tok["access_token"], "tools/list").status_code == 401   # rotated out
    assert rpc(http, new["access_token"], "tools/list").status_code == 200
    grant = signed_in(http).get("/api/agents").json()["agents"][0]["id"]
    assert http.delete(f"/api/agents/{grant}", headers={"X-Admin": "1"}).status_code == 200
    assert rpc(http, new["access_token"], "tools/list").status_code == 401
    # Another user can't see or revoke it.
    assert signed_in(http, {**ALICE, "sub": "bob"}).get("/api/agents").json()["agents"] == []


def test_agent_attribution_and_decode_compaction():
    p = Principal("g", ALICE, "Claude Code")
    assert p.created_by == f"{AGENT_PREFIX}Claude Code (alice@example.com)"
    assert compact_decode({"Make": "HONDA", "Trim": "", "Turbo": "Not Applicable", "Doors": "4", "X": None}) == \
        {"Make": "HONDA", "Doors": "4"}


def test_mcp_off_without_https_or_sign_in():
    assert install_mcp(FastAPI(), {**ENV, "PUBLIC_URL": "http://admin.gyopart.local"}) is None
    assert install_mcp(FastAPI(), {"PUBLIC_URL": BASE}) is None
