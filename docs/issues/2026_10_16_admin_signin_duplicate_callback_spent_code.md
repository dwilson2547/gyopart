# A duplicate sign-in callback re-used a spent authentik code, so a successful prod sign-in ended on "authentik refused the sign-in code"

**Date:** 2026-10-16 (UTC; 2026-10-15 evening US time)  
**Component:** `junkyard-platform/admin_api/auth/web.py` — `install.oidc_callback`, `install.guard`; `junkyard-platform/admin_api/auth/oidc.py` — `finish`  
**Severity:** Medium — the first sign-in to the new prod admin (https://gyopart-admin.danwils.com) showed a dead-end error page even though the sign-in had succeeded server-side; refreshing could not recover (the code is single-use). No data exposure; a fresh sign-in worked.

---

## Observed symptom

Right after the admin rewrite went to prod, the user signed in and landed on

```
https://gyopart-admin.danwils.com/api/auth/oidc/callback?code=9886125c…&state=vj3qQQ…
{"detail":"authentik refused the sign-in code"}        (HTTP 401)
```

Refreshing returned the same 401. It looked like the earlier scrape-job-manager sign-in failure (different
message: that one was the JWKS fetch, `infra/cluster-config/docs/notes/authentik-oidc-issuer-keeps-its-trailing-slash-new-client-se.md`).

---

## Root cause

### The callback request for one code arrived twice; the second exchange failed

authentik's server log, ordered by time (request ids abbreviated):

```
01:03:58.191  /application/o/authorize  state=vj3qQQ   302  (session: already signed in to authentik)
01:03:59.478  /application/o/token                     200  oauth_client_secret   <- code 9886… exchanged OK
01:04:00.121  /application/o/gyopart-admin/jwks/       200                        <- admin verifying the ID token
01:04:00.907  "Code does not exist"  code=9886…                                   <- same code, second time
01:04:00.910  /application/o/token                     400                        request_id 563efde8…
```

Authorization codes are single-use. The first callback request exchanged the code and would have set the
session cookie, but its response never reached the browser; a duplicate request for the same callback URL
(~1.4 s later) tried the spent code, got `invalid_grant`, and `oidc_callback` returned the raw 401. That 401
is the page the user saw. The two later callback lines in the admin log with the same code were refreshes of
the error page. What re-sent the request (browser or proxy chain) isn't visible in either log.

### Every signed-out GET started a sign-in, including background requests

The guard redirected any signed-out GET outside `/api` to the login route, so the browser's automatic
`/favicon.ico` fetch started its own sign-in (admin log: `GET /api/auth/oidc/login?next=%2Ffavicon.ico`), as
did a burst of seven sign-in starts within six seconds a few minutes earlier (authentik: authorize requests
00:56:57–00:57:03, each a new state). Each start overwrites the short-lived flow cookie (state, nonce, PKCE
verifier), so a real callback arriving after one of those fails as "came from another window". This didn't
cause the failure above, but it is the same class: a background request breaking the sign-in in progress.

```python
# before (guard)
if request.method == "GET" and not path.startswith("/api/") and path != "/api":
    return RedirectResponse(f"{LOGIN}?next=…")
```

### A failed callback was a dead end

`oidc_callback` turned any `SignInRefused` into `{"detail": …}` with 401, with no way forward from the page
and no check whether the browser was in fact already signed in.

---

## Troubleshooting steps taken

1. **Admin log for the token exchange** — `oidc: token endpoint 400: invalid_grant … does not match the
   redirection URI … or was issued to another client`. Ruled out the JWKS/User-Agent problem from sjm (that
   fails later, at verification, with a different message).

2. **Client secret and redirect URI** — the bogus-code probe against the token endpoint returned
   `invalid_grant` (not `invalid_client`), and the authorize request carried the exact registered redirect URI.
   Ruled out secret and redirect mismatches.

3. **authentik's log for the failing request id** — "Code does not exist" for code 9886…, and an earlier
   successful (200) token exchange 1.4 s before, after the authorize for the same state. Ruled in: the code was
   used twice.

4. **Every callback line in the admin log** — the failing code appeared three times, all 401: the duplicate
   plus two refreshes. A later sign-in (state wnHB27) succeeded (307 into the app).

5. **Sign-in starts in both logs** — found `/favicon.ico` starting a sign-in and the 00:57 burst; identified the
   flow-cookie overwrite as a second, latent failure mode.

---

## Fix

### `admin_api/auth/web.py` `guard` — only page navigations start a sign-in

```python
def is_navigation(request: Request) -> bool:
    mode = request.headers.get("sec-fetch-mode")
    if mode is not None:
        return mode == "navigate"
    return "text/html" in request.headers.get("accept", "")

if request.method == "GET" and not path.startswith("/api/") and is_navigation(request):
    return RedirectResponse(f"{LOGIN}?next=…")
# everything else signed-out -> 401
```

Background fetches (favicon, images, scripts) now get 401 and can't overwrite the flow cookie.

### `admin_api/auth/web.py` `oidc_callback` — recover instead of dead-ending

On `SignInRefused` (or `?error=` from authentik):

1. already signed in (valid session cookie) → continue to the page: a duplicate after a sign-in that worked;
2. otherwise restart the sign-in once, marked by a 2-minute `gya_retry` cookie; with authentik's session alive
   the retry is instant and invisible;
3. a second failure shows a readable "Sign-in didn't complete" page with a Try again link.

A success clears the retry marker. `oidc.flow_next` recovers the return-to page from the flow cookie for these
paths.

Shipped as admin-api `sha-355b70fb7b49`: dev first (navigation → sign-in, favicon → 401, spent code → silent
restart, spent code with the retry marker → readable page), then prod (cherry-picked onto main); replaying the
user's exact failed callback URL in prod now restarts the sign-in.

---

## Files changed

- `junkyard-platform/admin_api/auth/web.py` — `is_navigation`, `_failed_page`, `install.oidc_callback`, `install.guard`
- `junkyard-platform/admin_api/auth/oidc.py` — `flow_next`
- `junkyard-platform/tests/test_admin_auth.py` — navigation-only sign-in starts, one quiet retry then the readable page, duplicate after a successful sign-in
- `helm/gyopart/values.yaml` — `images.adminApi: sha-355b70fb7b49`

## Follow-ups (done 2026-10-16)

- Ported to the scrape-job-manager UI (web-scrapers/scrape-job-manager b422c0b, UI image sha-b422c0b2b63d): the
  same callback recovery. Its server only guards /api (the SPA isn't gated), so the favicon case didn't apply.
- Both SPAs: only the first 401 navigates to sign-in. Concurrent API calls each starting one were the likely source
  of the 7-in-6-seconds burst (admin-api sha-313aed947b12).
- Cloudflare caching: both SPA routes now 404 missing files with an extension and send the shell as no-store
  (admin-api sha-f9c82e4c01a3). Cloudflare still answers /robots.txt itself (its managed content-signals file).
