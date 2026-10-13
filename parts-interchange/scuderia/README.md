---
tier: experiment
---

# Scuderia collection prototype

Browser-transport collector for selected Scuderia OEM catalog variants, categories,
and diagrams. Outputs a lossless JSONL journal; **does not write to a database,
change gyopart's schema, or register fleet jobs**.

## Status

Verified recon: three diagrams across Ferrari, Lamborghini, and McLaren yielded
107 membership rows with stable identities on 15 browser requests. See
[the assessment](../docs/topics/scuderia-scrape-assessment.md).

The prototype parser is covered by a captured 69-row Ferrari table and focused
tests. The initial standalone cold-browser run did **not** establish dependable
access: the operator reported repeated Cloudflare validation on robots.txt, and
the run was stopped. Successful MCP reconnaissance is not proof that a separately
launched automated Chrome behaves identically.

**Verified live collection:** an isolated Browserless **2.57.0**, running Chrome
**156.0.8078.4**, collected all three diagrams and **107 membership rows** in four
fresh runs. Three runs used direct networking; the fourth used the fleet's
existing VPN proxy. Two direct runs followed a real Browserless service restart.
Row IDs, callout strings, site part IDs, OEM numbers, URLs, and image hashes
matched across runs and against recon. All three GIFs are in imgcache. Resume
skipped all three completed diagrams without target requests or journal changes.

**Explicit CDP access remains required.** The collector does not implicitly open
local Chrome, export/inject clearance cookies, implement a CAPTCHA solver, or
retry a failed bootstrap. The tested launch configuration reused the existing
fleet's headed/window-size/`AutomationControlled` settings; no injected
fingerprinting code, CAPTCHA provider credentials, or managed solving was used.

The shared cluster service still runs Browserless **1.61.1** with Chrome
**121.0.6167.85**. Both its ordinary headed configuration and the existing fleet
configuration timed out on robots.txt; the latter observed navigation 307 then
403. **That deployment was not upgraded.** The working comparison is not a
claim that Scuderia is deployed or operational in the cluster fleet. Long-duration
and broad-catalog operation remain unverified.

The deployed service rejected `Browserless.solveCaptcha` with a CDP
method-not-found error on a blank page. The
[current Browserless CAPTCHA documentation](https://docs.browserless.io/baas/bot-detection/captchas)
describes `solveCaptchas=true` and solver commands on managed endpoints; that
does not make the feature available in the deployed legacy image. No CAPTCHA
solver, paid service, or shared-cluster upgrade has been enabled. The successful
current-browser runs did not require that solver feature.

## Install and run

Requires Python 3.11+, Docker for the verified isolated runtime, and reachable
scrape-stack services. Start the pinned Browserless image in another terminal:

```bash
docker run --rm --name scuderia-browserless \
  --publish 127.0.0.1:19301:3000 --shm-size=1g --memory=2g --cpus=2 \
  --env CONCURRENT=1 --env TIMEOUT=240000 \
  ghcr.io/browserless/chromium@sha256:c4fd6493ff97936eb62cb35bbc19a428dda3d30905c3a59a28d9620f29b85db1
```

This is the image tested above, not a replacement for the shared cluster service.
Binding only to loopback avoids exposing an unauthenticated browser service.
Stop that specific container with `docker stop scuderia-browserless`.
From the collector directory:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

export WEBCACHE_URL=http://webcache.scrapestack.local
export IMGCACHE_URL=http://imgcache.scrapestack.local
export REQUEST_AUTH_SERVER_URL=request-auth-server.scrapestack.local:9000
# Optional: use the existing VPN proxy via its verified workstation NodePort.
# Omit this variable for the independently verified direct-network configuration.
export BROWSER_PROXY_URL=http://192.168.0.35:30008
export BROWSERLESS_URL="$(python - <<'PY'
import json
import os
from urllib.parse import urlencode
launch = {
    "headless": False,
    "args": ["--window-size=1400,1000",
             "--disable-blink-features=AutomationControlled"],
}
if os.environ.get("BROWSER_PROXY_URL"):
    launch["args"].append("--proxy-server=" + os.environ["BROWSER_PROXY_URL"])
print("ws://127.0.0.1:19301/chromium?" + urlencode({
    "launch": json.dumps(launch), "timeout": 240000,
}))
PY
)"

.venv/bin/python scraper.py --timeout 60 --output output/sample.jsonl
```

The service hostnames, VPN NodePort, and current Browserless endpoint above were
verified during development. The four-minute session lifetime is for a bounded
smoke run, not a full catalog crawl; increase it deliberately for larger bounds.
There is no implicit local-browser fallback if the configured runtime is absent.

For deployment comparison only, the legacy service can be reached with
`kubectl port-forward -n scrape-stack service/browserless 19300:3000`.
From inside the cluster, the production browser service is
`ws://browserless.scrape-stack.svc.cluster.local:3000`; the existing dev fleet uses
`ws://browserless.scrapestack-dev.svc.cluster.local:3000`. These addresses are
verified in the gyopart Helm configuration; Kubernetes service DNS is not a
workstation endpoint. Inside the cluster the existing VPN proxy address is
`http://nordvpn-proxy-entrypoint.vpn.svc.cluster.local:8118`. These legacy browser
addresses are **not** the successful current-image endpoint used above.

A missing browser endpoint remains an explicit CLI error, not an implicit fresh
local browser launch. There is no Browserless ingress in the verified production
deployment, so `browserless.scrapestack.local` must not be assumed to work.

Default targets are the three diagram URLs from recon. Scope is always bounded:
three new diagrams and 50 catalog pages by default. To traverse a selected
variant rather than a known diagram:

```bash
.venv/bin/python scraper.py \
  --seed https://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22 \
  --max-diagrams 2 --max-pages 20 --output output/ferrari.jsonl
```

Repeat `--seed` for additional variant/category/diagram URLs. No ID enumeration
or automatic all-marque crawl occurs. Traversal is depth-first in seed order, so
the diagram limit may be exhausted before a later seed is reached.

| Option | Behavior |
|---|---|
| `--output` | Append/resume one JSONL journal; exclusively locked while running |
| `--max-diagrams`, `--max-pages` | Positive per-run bounds |
| `--max-age` | Webcache freshness in seconds; default 82800; 0 requests fresh misses |
| `--bucket` | Cache namespace; default `scuderia`, overridable with `CACHE_BUCKET` |
| `--metadata-only` | Keep image references without downloading/storing image bytes |
| `--timeout` | Single browser startup/fetch wait, default 30 seconds; no retries |
| `--cdp-url` | Required ordinary browser connection; defaults to `BROWSERLESS_URL` |

Stop with Ctrl-C. Rerun the same command to resume. To perform fresh comparison
runs, use different output files and `--max-age 0`; otherwise completion markers
intentionally skip previously collected diagrams. Image cache hits remain cache
hits regardless of HTML max age.

## Output and gyopart compatibility

Each diagram is a journal transaction:

1. `diagram`: compatible manufacturer/car/category/subcategory/diagram/image
   fields plus source variant identity and percentage hotspot geometry.
2. `diagram_part`: one record per membership row, carrying the part's OEM
   manufacturer, URL, number, title, and description; `part_index` remains a string.
   Source metadata preserves row/site IDs, price/stock text, market notes,
   quantity on the drawing, and enquiry-only state.
3. `diagram_complete`: commits that batch after every preceding record was
   flushed and fsynced.

**Only consume batches having a completion marker.** Interrupted batches remain
in the file and are retried with a new batch ID; do not ingest every raw part line
as an independent committed result. A malformed, unterminated final line is
removed with a warning during recovery. Corrupt complete lines or invalid
completion sequences cause an explicit failure.

The mapping follows `parts_interchange_common/models.py`, but this is **not** an
ORM dump or a ready-to-run DB loader. Unknown year/trim/engine fields are null.
Source market notes are membership-specific, not assumed global `Part.notes`.
Sale price is not mapped to MSRP, `$` is not guessed to be a particular ISO
currency, and missing price/stock never becomes zero/out-of-stock.

Gyopart's `diagram_parts` primary key allows only one row per diagram/part pair;
Scuderia may have several rows or callouts for that same pair. The journal keeps
all of them, plus hotspots and quantities. A future DB adapter must decide how to
retain those details before ingesting them. No migration is generated here.

## Network and failure behavior

- Webcache lookup precedes catalog/robots fetches; only validated responses are
  cached. Cached robots text can establish a new collector tab's origin locally
  without revisiting the target's robots endpoint.
- Intercepted site/challenge requests acquire request-auth permits and report
  their observed response status. Cache service calls and locally fulfilled
  cached robots do not acquire target permits. Automatic navigation redirects
  are not independently intercepted/paced by Playwright; their statuses are
  tracked separately for bootstrap validation and timeout diagnostics.
- Configure at least the site's observed one-second crawl delay in request-auth.
  There is no competing local delay/backoff state or proxy rotation.
- Unrelated third-party requests are blocked. Site resources and Cloudflare's
  normal challenge host remain permitted. Only the collector's tab is routed;
  other tabs in the supplied browser context are not modified or closed.
- Image lookup/store uses imgcache's `hash` field, not webcache's `content_hash`.
  Source media is fetched through the browser
  under permits, limited to 20 MiB, and must have an image content type.
- Unresolved startup challenges, catalog 403/429, robots restrictions, malformed
  tables, wrong selected vehicles, and cache/service failures stop the run.
  Incomplete diagrams do not get completion markers.
- Exit 0 prints collection counters and intercepted-response status counts,
  not a complete physical-request trace of automatic redirect chains.
  `page_limit`/`diagram_limit` mean bounded progress, not full-catalog completion.
  Exit 1 indicates an explicit collection/service failure; CLI errors exit 2.

## Focused tests

```bash
python -m pytest -q tests
```

Tests require pytest in the development environment; it is not a runtime
dependency. The fixture contains selected catalog controls, parts-table markup,
image references, and hotspot metadata from the existing working browser page,
not image bytes, cookies, or browser storage state.

Before fleet integration, adopt and verify a current cluster browser runtime,
review redirect permit/pacing coverage, collect ten diagrams per sampled marque,
and repeat over 24 hours. The bounded collection proof is complete; that broader
operational gate is not.
