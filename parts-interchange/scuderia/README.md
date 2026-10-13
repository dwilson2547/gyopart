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

**Explicit CDP access is now required.** Use a dedicated ordinary Chrome session
that has legitimate site access, or an explicitly configured browserless session.
The collector does not implicitly open local Chrome, export/inject clearance
cookies, add stealth flags, solve challenges, or retry a failed bootstrap.
Remote/headless and long-duration prototype operation remain unverified.

## Install and run

Requires Python 3.11+ and reachable scrape-stack services. From this directory:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

export WEBCACHE_URL=http://webcache.scrapestack.local
export IMGCACHE_URL=http://imgcache.scrapestack.local
export REQUEST_AUTH_SERVER_URL=request-auth-server.scrapestack.local:9000
# Set BROWSERLESS_URL to YOUR verified CDP endpoint; do not guess its address.
# A local, explicitly configured Chrome debugging endpoint can also be supplied
# using --cdp-url. Use a dedicated browser profile, not a personal browsing session.

.venv/bin/python scraper.py --output output/sample.jsonl
```

The service hostnames above were reachable during development. No working CDP
endpoint has been verified for the standalone prototype. A missing browser
endpoint is an explicit CLI error, not an implicit fresh browser launch.

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
- Every allowed real browser request, including bootstrap/challenge subrequests,
  acquires a request-auth permit and reports its actual response status. Cache
  service calls and locally fulfilled cached robots do not acquire target permits.
- Configure at least the site's observed one-second crawl delay in request-auth.
  There is no competing local delay/backoff state or proxy rotation.
- Unrelated third-party requests are blocked. Site resources and Cloudflare's
  normal challenge host remain permitted. Only the collector's tab is routed;
  other tabs in the supplied browser context are not modified or closed.
- Image lookup/store uses imgcache. Source media is fetched through the browser
  under permits, limited to 20 MiB, and must have an image content type.
- Unresolved startup challenges, catalog 403/429, robots restrictions, malformed
  tables, wrong selected vehicles, and cache/service failures stop the run.
  Incomplete diagrams do not get completion markers.
- Exit 0 prints collection counters and actual target response-status counts.
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

Before fleet integration, validate a correctly configured CDP runtime, process
restarts, ten diagrams per sampled marque, and repeated runs over 24 hours.
