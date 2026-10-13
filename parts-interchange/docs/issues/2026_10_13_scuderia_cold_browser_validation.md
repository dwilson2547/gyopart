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

### Image-cache metadata was mistaken for webcache metadata

Once a current Browserless session obtained valid catalog data, the collector
successfully stored the Ferrari GIF but rejected its cache response. It looked
for webcache's `content_hash`; the deployed imgcache lookup/store contract uses
`hash`. Earlier mocked image-cache responses repeated that incorrect assumption.
This was a collection integration defect, not a site-access failure.

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
10. **Matched the existing fleet's browser/VPN settings and added diagnostics** —
    the legacy service still timed out, with navigation statuses `[307, 403]` and
    zero active permits at failure. The default request-status counter did not
    include every automatic redirect response, so it was not a complete network
    trace.
11. **Ran an isolated current Browserless image** — used a loopback-only,
    resource-limited Docker container, Browserless 2.57.0 / Chrome 156.0.8078.4,
    without changing the shared cluster deployment. Browser startup and Ferrari
    collection succeeded without operator validation or a CAPTCHA provider.
    Actual imgcache metadata exposed the incorrect hash-field assumption.
12. **Corrected the imgcache contract and verified collection** — four fresh
    successful runs each collected 69 Ferrari, 11 Lamborghini, and 27 McLaren
    membership rows. Three used direct networking and one used the existing
    fleet VPN through its NodePort. Two direct runs followed a real container
    restart. Each output contained three complete diagram batches and 113 lines.
13. **Checked identities, media, and resume** — the three direct-run journals
    matched original recon identities and each other's image hashes. Imgcache
    contained all three nonempty GIFs. A resume run skipped all completed
    diagrams, performed no target requests, and left the journal unchanged.
14. **Rejected a body-completion wait experiment** — waiting on
    `Response.finished()` while holding permits caused a reproduced startup
    timeout and Playwright target-closed errors. That experiment was removed;
    the subsequent header-response path completed both post-restart runs.

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

### `Collector.image` — use the actual imgcache hash contract

Use imgcache's `hash` for both lookup hits and successful stores. Keep explicit
failure on missing/invalid metadata. Tests now cover the actual hit/miss shape
and reject the erroneous webcache-only field.

### `BrowserTransport.fetch` — actionable bounded timeout

Report observed navigation statuses, intercepted-response counts, and the active
permit count. Do not log CDP credentials, cookies, storage state, or challenge
tokens. Navigation and permit-status counters cover different surfaces because
automatic redirect requests are not independently routed by Playwright.

### Runtime verification — current image collects, legacy cluster remains blocked

The pinned isolated image now has a demonstrated collection path, including the
existing VPN network, process restart, and resume. The shared legacy deployment
still fails startup. The precise original validation-loop cause remains
**unverified**; the current-image comparison does not prove one individual
browser flag or browser-version difference was the sole cause.

The deployed legacy service does not expose the documented
`Browserless.solveCaptcha` command. Adding `solveCaptchas=true` cannot be treated
as a verified fix for that image. Using an offering with the documented solver
would be a separate runtime/service decision; neither a shared cluster upgrade
nor a paid service was activated.

The README now provides the pinned, verified current-image command and identifies
the existing fleet service separately. It reuses the fleet's launch settings;
no bespoke challenge-solving code or managed CAPTCHA service was added.
Broad crawling, redirect permit/pacing coverage, and 24-hour reliability remain
future fleet-adoption gates, not claims established by these samples.

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
- `scuderia/scraper.py` — correct imgcache hash field and sanitized timeout diagnostics
- `scuderia/tests/` — parsing, recovery, robots/cache behavior, permit-status and image-contract coverage
- `scuderia/README.md` — pinned current runtime, verified collection, and legacy deployment distinction
