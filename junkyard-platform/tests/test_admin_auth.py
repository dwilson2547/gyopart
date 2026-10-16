"""Phase 4: authentik sign-in in front of the admin (admin_api/auth). A small app with the guard installed stands in
for the real one: page loads go to sign-in, API calls get 401, writes need the X-Admin (or htmx) header."""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from admin_api.auth import session
from admin_api.auth.web import install, who

ENV = {"OIDC_ISSUER": "https://auth.example/application/o/gyopart-admin/", "OIDC_CLIENT_ID": "gyopart-admin",
       "OIDC_CLIENT_SECRET": "s3cret", "PUBLIC_URL": "https://gyopart-admin.example"}


def make_app(env=ENV):
    app = FastAPI()
    assert install(app, env) is bool(env.get("OIDC_ISSUER"))

    @app.get("/api/thing")
    def thing(request: Request):
        return {"by": who(request)}

    @app.post("/api/thing")
    def write(request: Request):
        return {"by": who(request)}

    @app.get("/admin/ui/rules")
    def old_page():
        return {"page": "old"}

    @app.get("/assets/app.js")
    def asset():
        return {"js": True}

    return app


@pytest.fixture()
def client():
    # base_url = the public host, as behind the real ingress
    return TestClient(make_app(), follow_redirects=False, base_url="https://gyopart-admin.example")


def signed_in(client):
    client.cookies.set(session.COOKIE, session.sign("s3cret", {"sub": "u1", "name": "Dan", "email": "dan@example"}))
    return client


NAV = {"Sec-Fetch-Mode": "navigate"}


def test_signed_out_page_load_goes_to_sign_in_and_back(client):
    r = client.get("/admin/ui/rules?status=x", headers=NAV)
    assert r.status_code == 307
    assert r.headers["location"] == "/api/auth/oidc/login?next=%2Fadmin%2Fui%2Frules%3Fstatus%3Dx"


def test_signed_out_api_is_401_but_config_me_and_assets_are_open(client):
    assert client.get("/api/thing").status_code == 401
    assert client.post("/api/thing", headers={"X-Admin": "1"}).status_code == 401
    assert client.get("/api/config").json()["oidc"] is True
    assert client.get("/api/me").json() == {"user": None, "oidc": True}
    assert client.get("/assets/app.js").status_code == 200


def test_background_requests_never_start_a_sign_in(client):
    """A favicon or image fetch that started a sign-in would overwrite the flow cookie of the real one."""
    r = client.get("/favicon.ico", headers={"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "image"})
    assert r.status_code == 401
    assert client.get("/admin/ui/rules", headers={"Accept": "text/html"}).status_code == 307   # old clients


def test_signed_in_reads_and_writes_record_who(client):
    signed_in(client)
    assert client.get("/api/thing").json() == {"by": "dan@example"}
    assert client.get("/api/me").json()["user"]["name"] == "Dan"
    assert client.post("/api/thing", headers={"X-Admin": "1"}).json() == {"by": "dan@example"}


def test_writes_need_the_csrf_header(client):
    signed_in(client)
    assert client.post("/api/thing").status_code == 403
    assert client.post("/api/thing", headers={"HX-Request": "true"}).status_code == 403   # the htmx pages are gone


def test_other_hosts_are_sent_to_the_public_host():
    lan = TestClient(make_app(), follow_redirects=False, base_url="http://admin.gyopart-dev.local")
    r = lan.get("/vehicles/42?x=1", headers=NAV)
    assert r.status_code == 307 and r.headers["location"] == "https://gyopart-admin.example/vehicles/42?x=1"


def test_auth_off_without_issuer():
    c = TestClient(make_app({}))
    assert c.get("/api/thing").json() == {"by": "admin"}
    assert c.post("/api/thing").status_code == 200


def test_callback_sets_a_secure_session_and_lands_on_the_page(client, monkeypatch):
    from admin_api.auth import oidc
    monkeypatch.setattr(oidc.Provider, "metadata", lambda self: {"authorization_endpoint": "https://auth.example/authorize"})
    monkeypatch.setattr(oidc.Provider, "exchange", lambda self, code, verifier, uri: {"id_token": "t"})
    nonce = {}
    monkeypatch.setattr(oidc.Provider, "verify",
                        lambda self, tok, n: {"sub": "u1", "name": "Dan", "email": "dan@example", "nonce": nonce.setdefault("n", n)})
    login = client.get("/api/auth/oidc/login", params={"next": "/vehicles/42"})
    state = login.headers["location"].split("state=")[1].split("&")[0]
    done = client.get("/api/auth/oidc/callback", params={"code": "c", "state": state},
                      headers={"Cookie": f"{oidc.FLOW_COOKIE}={login.cookies[oidc.FLOW_COOKIE]}"})
    assert done.status_code == 307 and done.headers["location"] == "/vehicles/42"
    assert done.headers["set-cookie"].startswith(session.COOKIE) and "secure" in done.headers["set-cookie"].lower()


def _spent_code(monkeypatch):
    """authentik answering 'Code does not exist' (a duplicate callback re-using a spent code)."""
    from admin_api.auth import oidc
    monkeypatch.setattr(oidc.Provider, "metadata", lambda self: {"authorization_endpoint": "https://auth.example/authorize"})

    def refuse(self, code, verifier, uri):
        raise oidc.SignInRefused("authentik refused the sign-in code")
    monkeypatch.setattr(oidc.Provider, "exchange", refuse)
    return oidc


def test_failed_callback_retries_the_sign_in_once_then_explains(client, monkeypatch):
    oidc = _spent_code(monkeypatch)
    login = client.get("/api/auth/oidc/login", params={"next": "/mappings"})
    state = login.headers["location"].split("state=")[1].split("&")[0]
    flow = f"{oidc.FLOW_COOKIE}={login.cookies[oidc.FLOW_COOKIE]}"
    first = client.get("/api/auth/oidc/callback", params={"code": "spent", "state": state}, headers={"Cookie": flow})
    assert first.status_code == 307 and first.headers["location"] == "/api/auth/oidc/login?next=%2Fmappings"
    assert "gya_retry=1" in first.headers["set-cookie"]
    again = client.get("/api/auth/oidc/callback", params={"code": "spent", "state": state},
                       headers={"Cookie": f"{flow}; gya_retry=1"})
    assert again.status_code == 401 and "text/html" in again.headers["content-type"]
    assert "Try again" in again.text and "next=%2Fmappings" in again.text


def test_duplicate_callback_after_a_successful_sign_in_just_continues(client, monkeypatch):
    _spent_code(monkeypatch)
    signed_in(client)
    r = client.get("/api/auth/oidc/callback", params={"code": "spent", "state": "x"})
    assert r.status_code == 307 and r.headers["location"] == "/"
