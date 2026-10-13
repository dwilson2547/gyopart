# Implicit cold-browser startup requires repeated validation instead of reaching the catalog

**Date:** 2026-10-13

**Component:** `scuderia/scraper.py` - `BrowserTransport._start`, `fetch`, `Collector.load_robots`

**Severity:** Medium — the prototype blocked on startup and repeatedly required operator attention.

---

## Observed symptom

During the first standalone prototype run, the operator reported manually
completing Cloudflare validation twice on Scuderia's robots.txt and seeing the
page reload. The run was stopped before successful collection was established.
The existing MCP browser still displayed the Ferrari diagram and its 69 rows.

---

## Root cause

### Successful reconnaissance did not establish equivalent standalone browser access

Recon used an ordinary browser session; a CDP command in that browser confirmed
that `--enable-automation` was not set. The first prototype instead implicitly
launched a new Chrome through Playwright with a fresh context. It therefore did
not reuse the working browser/runtime or its session state.

The prototype contained one startup navigation and no explicit reload/retry loop.
The precise reason that the site's validation did not persist in the new runtime
remains **unverified**. Runtime differences and permit-gated challenge traffic
must not be presented as proven individual causes of Cloudflare's behavior.

### Robots cache hits did not establish a browser origin

The browser starts on about:blank. A cached robots response should not cause
another real robots navigation solely to establish origin before subsequent
browser fetches. Reusing cached content locally avoids that unnecessary network
step, while still requiring legitimate browser access for actual catalog requests.

---

## Troubleshooting steps taken

1. **Stopped the standalone run** — prevented further operator intervention while
   the startup behavior was unresolved.
2. **Checked the existing browser page** — confirmed the previously working
   Ferrari diagram remained accessible with 69 parts rows.
3. **Compared startup paths** — identified the implicit fresh local Chrome launch;
   the existing MCP browser reported no automation flag.
4. **Inspected navigation logic** — found no application-level reload loop.
   The exact validation/reload mechanism was not established.
5. **Ran captured-page and mocked-runtime tests** — verified parser, journal,
   cache, robots restrictions, and real-status permit handling without asking the
   operator to solve further challenges.
6. **Inspected the existing fleet and live deployment** — gyopart's Parts Direct
   scraper uses headed Browserless over the internal service on port 3000.
   The production deployment had no Browserless ingress. Its running package
   reported `browserless-chrome` 1.61.1 and Chrome 121.0.6167.85, despite the
   chart's `browserless/chrome:latest` tag. The running image digest was
   `sha256:57d19e414d9fe4ae9d2ab12ba768c97f38d51246c5b31af55a009205c136012f`.
7. **Checked the deployed solver capability without visiting Scuderia** —
   connected to a blank headed session through a temporary service port-forward.
   `Browserless.solveCaptcha` returned CDP method-not-found. No environment
   variable names matching CAPTCHA, LICENSE, or STEALTH were present; no secret
   values or browser cookies were inspected or exported.
8. **Ran one bounded cluster collector smoke** — used the existing Browserless
   service with `headless=false`, a 180-second session lifetime, real cache and
   request-auth clients, `--max-age 0`, and the existing
   `scuderia-recon-20261013` bucket. The robots lookup missed and the collector
   exited 1 with `browser_timeout` after its 30-second page/challenge wait.
   The output journal contained zero records. There was no application retry,
   local Chrome window, or request for manual validation.
9. **Reviewed current Browserless documentation and the supplied ZenRows article** —
   the documented managed-endpoint solver API is not exposed by this deployment.
   The article's browser-transport/session distinctions are relevant; its managed
   vendor success claims do not establish access through the existing runtime.

---

## Fix

### `BrowserTransport._start` — explicit runtime, isolated collector tab

Require an explicitly configured CDP endpoint. Reuse its existing context when
available, open one collector-owned tab, and apply routing only to that tab.
Do not close the supplied browser or its existing context/tabs. Remove implicit
local Chrome launches. No stealth flags or challenge-solving services are added.

### `Collector.load_robots`, `BrowserTransport.fetch` — cache-aware bootstrap

Retain validated cached robots text and serve it locally when a new tab needs a
same-origin document. Do not make another real robots request on that cache hit.
Real catalog/media requests still need browser access and request-auth permits.
An unresolved challenge remains an explicit bounded failure with no retry.

### Runtime verification — connection confirmed, collection still blocked

Captured-page and mocked-runtime tests pass. The existing cluster CDP endpoint
now has a verified connection path, but the standalone collector still has no
successful live collection. The last smoke did not record page title or HTTP
status details at failure, so the specific cause of its timeout remains
**unverified**; an old browser, challenge behavior, or permit-gated subrequests
must not individually be asserted as the cause.

The deployed legacy service does not expose the documented
`Browserless.solveCaptcha` command. Adding `solveCaptchas=true` cannot be treated
as a verified fix for that image. Using an offering with the documented solver
would be a separate runtime/service decision; neither a shared cluster upgrade
nor a paid service was activated.

The README now uses the existing fleet's service rather than asking the operator
to identify a browser. No custom Cloudflare bypass has been implemented.

Sources:
[Browserless CAPTCHA API](https://docs.browserless.io/baas/bot-detection/captchas),
[user-supplied ZenRows article](https://www.zenrows.com/blog/bypass-cloudflare),
`web-scrapers/scrape-stack/helm/scrape-stack/templates/browserless.yaml`,
and `automotive/gyopart/helm/gyopart/values-prod.yaml` /
`values-dev.yaml` in the workspace. Live package/CDP checks and the failed-run
log are session-local evidence, not evidence of successful collection.

---

## Files changed

- `scuderia/scraper.py` — startup, browser ownership, cached-robots bootstrap, CLI requirements
- `scuderia/tests/` — parsing, recovery, robots/cache behavior, permit-status coverage
- `scuderia/README.md` — explicit runtime setup and unresolved live-access limitation
