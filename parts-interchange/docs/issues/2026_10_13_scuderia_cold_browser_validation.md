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

### Runtime verification — still incomplete

Captured-page and mocked-runtime tests pass. A working CDP endpoint and a full
standalone live collection remain unverified; do not claim production readiness
or infer it from successful MCP reconnaissance.

---

## Files changed

- `scuderia/scraper.py` — startup, browser ownership, cached-robots bootstrap, CLI requirements
- `scuderia/tests/` — parsing, recovery, robots/cache behavior, permit-status coverage
- `scuderia/README.md` — explicit runtime setup and unresolved live-access limitation
