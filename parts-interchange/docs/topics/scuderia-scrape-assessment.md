# Scuderia Car Parts: collection feasibility and proposed strategy

Recon: 2026-10-13. Scope: public original-equipment catalog, not tuning products,
database integration, fleet registration, or deployment.

## Decision

**Verified:** Parts and diagram metadata are extractable repeatedly through
ordinary Chrome, including two fresh empty browser contexts that completed the
initial challenge through the page's normal JavaScript without intervention.
**Not verified:** a restarted browser process, headless operation, long-duration
collection, or the fleet's runtime/network. Do not describe this as a
production-ready scraper.

**Proposed:** Use ordinary Chrome driven by Playwright, with a bounded wait for
normal startup navigation to settle. A persistent, legitimately established
browser profile can retain normal session state. Parse the HTML returned by browser requests; the
tested diagram tables are server-rendered, so individual pages do not require
executing their entire JavaScript/advertising stack. An initial homepage 403 is
not sufficient evidence of terminal failure: observe whether normal navigation
reaches the actual homepage within a bounded wait, without clicks or retries.
Stop explicitly on an unresolved challenge, a catalog 403, or a 429; do not use stealth, proxy rotation, challenge-solving
services, or repeated attempts to evade a block. If unattended access cannot be
established normally, request a catalog feed or crawler allowance from Scuderia.

## Verified collection evidence

Three rounds fetched each of these pages through same-origin browser `fetch`,
with `cache: "no-store"` and at least 1.1 seconds between requests. All nine
responses were HTTP 200 with `cf-cache-status: DYNAMIC`. SHA-256 hashes of
`row_id`, label, part number, description, notes, and diagram quantity matched
across rounds for each page. This was a short, same-session test, not a soak test.
Prices, availability, and hotspot coordinates were not included in those hashes.
Two additional fresh contexts collected the same three pages each with HTTP 200
and matching identity fields: **15/15 diagram-page requests succeeded** overall.
Each fresh context started without injected cookies or storage state.

| Vehicle / diagram | Parts-table rows | Distinct site part IDs | Collection checks passed |
|---|---:|---:|---:|
| Ferrari 458 Italia / Crankcase | 69 | 61 | 5/5 |
| Lamborghini Aventador LP700 Coupe / Water Pump | 11 | 11 | 5/5 |
| McLaren 12C Coupe / Heat Insulation | 27 | 26 | 5/5 |

Source pages:

- <https://www.scuderiacarparts.com/part-finder/ferrari/458/oe/22/2551/48748>
- <https://www.scuderiacarparts.com/part-finder/lamborghini/aventador/oe/181/3155/57087>
- <https://www.scuderiacarparts.com/part-finder/mclaren/12c/oe/837/7921/147505>

Each diagram's original GIF also returned HTTP 200 through browser `fetch`:

| Diagram | Response bytes | SHA-256 |
|---|---:|---|
| Ferrari | 163576 | `be169929d75b65bf5d9ab9fdaa2bc4af3c84b82c2f5a514b473696f7befa8740` |
| Lamborghini | 112520 | `768d5857c6ce265b5009d7ffbdc5c46216164462ca12f51aa39cabddc363f974` |
| McLaren | 636605 | `16c86d454898e562aa248966b7c8df1736a6880fc31aed8cfc92399402dadae6` |

The existing browser context contained an HTTP-only `cf_clearance` cookie;
its value was not exported. An initial test closed a fresh context immediately
after observing HTTP 403 and title `Just a moment...`; that was too early to
conclude startup was blocked. A subsequent fresh context was allowed to run
normal page JavaScript for 15 seconds and reached the homepage with HTTP 200.
Two further fresh contexts used a bounded 30-second wait for the real homepage;
both progressed through navigation statuses 307, 403, 200 and obtained clearance
normally in 3098 and 3396 milliseconds, respectively. They then fetched all three
sample diagrams successfully. No challenge clicks, stealth, cookie injection,
proxy changes, or request retries were used. These are isolated contexts in the
same Chrome 148 process, not independent process restarts.

A Python `requests` replay of the Ferrari diagram URL using the captured browser
headers but **no cookies** returned HTTP 403, `cf-mitigated: challenge`, and zero
parts rows. A cookie-bearing Python replay was not completed: the Playwright
server rejected the subprocess setup's dynamic import before making a request.
Thus neither cookie-free HTTP collection nor a browser-to-`requests` handoff
has been demonstrated. Do not assume clearance cookies are portable. The
successful transport is the actual browser, not merely a matching user-agent.

## Discovery and extraction

**Verified:** `/part-finder/` exposes a broader marque selector than the homepage
OEM links: 28 marque options were observed, including Bugatti and Pagani.
An option's presence does not establish diagram completeness for that marque.
Only Ferrari, Lamborghini, and McLaren diagram pages were sampled.

The tested catalog follows:

```text
/part-finder/{marque}
/part-finder/{marque}/{model}
/part-finder/{marque}/{model}/oe
/part-finder/{marque}/{model}/oe/{variant_id}
/part-finder/{marque}/{model}/oe/{variant_id}/{category_id}
/part-finder/{marque}/{model}/oe/{variant_id}/{category_id}/{diagram_id}
/part/{site_part_id}/{marque}/{part_number}/{description_slug}.html
```

**Proposed:** Discover URLs from the actual option values and links. Do not
enumerate numeric IDs, synthesize slugs, or assume a fixed variant/year mapping.
Preserve the selected option text and source URL at every level.

Observed selectors:

| Surface | Selector / extraction |
|---|---|
| Marques | `select[aria-label="Select Marque"] option[value]` |
| Models | `select[aria-label="Select Model"] option[value]` |
| Variants | `select[aria-label="Select Model Variant"] option[value]` |
| Categories | `select[aria-label="Select Main OE Parts Main Category"] option[value]` |
| Diagrams | `select[aria-label="Select Sub Category OE Parts"] option[value]` |
| Parts table | `#diagtable tr.diagrow` |
| Row identity / callout | `data-divid`, `data-labelcode` |
| Part links | `a.parturl` within the desktop number/description cells |
| Fitment notes | description link's `data-original-title`; mobile `a.notesurl` also exists |
| Diagram image | `.filter_diagimg img[src]` on the rendered Ferrari page; validate other templates |
| Hotspots | `a.custom-diaghotspot[data-labelcode]`, percentage coordinates in `style` |

In all three tested tables the cells were: selection control, callout, desktop
part number, desktop description, mobile duplicate, price, quantity on diagram,
order quantity, cart/enquiry action. Prefer mapping columns by table headers in
an implementation and reject unexpected layouts rather than silently misaligning
fields. The description-cell ID is repeated across rows; do not use it as a
globally unique ID.

Important verified edge cases:

- Ferrari has multiple rows for the same part ID and alternatives at a callout.
  Keep diagram membership/row context, not just a set of part numbers.
- Labels include leading zeros (`001`, `010`); keep strings.
- Desktop/mobile content duplicates links inside a single row. Extract once per
  `tr.diagrow`, not once per link or tooltip table.
- Hotspot labels can repeat with different coordinates. Preserve every actual
  position and its diagram context; do not collapse by label alone.
- Eight McLaren rows had price text `-`; enquiry actions also exist.
  Missing price is not zero, and missing stock text is not "out of stock."
- Ferrari notes include market restrictions, such as `Not for EU GS, UK`.
- Prices were displayed with `$`; an ISO currency, tax basis, and delivery
  region were not established. Keep the raw text until verified.
- A broad `img[src*="/images/diagrams/"]` also includes other diagrams'
  recommendation thumbnails. Use the main-diagram container, not all page images.

**Verified:** Sampled diagram tables were present in the HTML returned by
browser `fetch`, without rendering that fetched page. Network inspection on the
Ferrari diagram showed the document and GIF plus `/ajax/loadmainnav/` and
`/ajax/ga4eec/`; no separate parts-data JSON request was observed there.

**Verified:** The tested variant/category lists expose direct URLs in selects
and links. No pagination was seen in the sampled hierarchy or complete diagram
tables. Other marques/templates and product-detail pagination remain unverified.

## Robots, terms, and advertised API

**Verified:** `/robots.txt` initially returned a 403 on navigation, but a fetch
from the working browser context returned HTTP 200. Its wildcard rules do not
disallow the tested `/part-finder/`, `/part/`, or `/images/diagrams/` paths.
It declares `Crawl-delay: 1`. It disallows account, checkout, and several other
paths, including `/images/misc/*`; avoid placeholder images in that directory.
AI-specific allow rules are not a blanket data-reuse license.

**Verified:** `/terms-and-conditions/` returned HTTP 200. The reviewed page was
primarily sales terms; a keyword review found no explicit robot/scraping clause.
This is not a legal clearance or permission to republish diagram artwork.
Obtain appropriate permission before bulk diagram redistribution.

**Verified:** `/.well-known/openapi.json` and `/.well-known/ai-plugin.json`
redirect to a public AI-discovery service. The advertised OpenAPI paths are
`/business`, `/testimonials`, `/categories`, `/faq`, and `/search`. There is no
documented complete parts/diagram enumeration endpoint in that specification.
Its search describes curated business content, not a proven catalog feed.
Do not infer full coverage or diagram licensing from the API's general claims.

## Proposed collection-only prototype

Do this before any schema or fleet work:

1. Establish ordinary browser access in the intended runtime. Navigate to the
   homepage and wait, with a bounded timeout, for the actual homepage DOM/title;
   initial challenge responses must not be mistaken for final catalog results.
   Report observed statuses truthfully to request-auth. If using a persistent
   profile, treat it as sensitive state, excluded from Git and logs. Restart
   the browser process and verify it still works; stop and seek site cooperation
   if a challenge does not resolve normally.
2. Traverse only discovered same-origin catalog URLs with one browser worker.
   Check `WebCacheClient.get` before each target request. Acquire request-auth
   permits for actual browser HTML/media requests, report real statuses, and
   honor the observed crawl delay through centralized pacing. Browser navigation
   subrequests need explicit permit handling too; one navigation permit must
   not be mistaken for authorization of every asset request.
3. Reject challenge pages, non-200 responses, wrong page types, missing tables,
   or missing part identities. Never cache a challenge page as valid HTML or
   mark a failed diagram complete. Surface schema drift separately from access
   failures. Do not introduce a competing local backoff/ban registry.
4. Append and flush JSONL records while collecting: source URL/time, marque,
   model, variant, category, diagram ID/title, row ID, label string, site part ID,
   part number, description, notes, raw price/stock, diagram quantity, and
   enquiry-only flag. Preserve diagram image URLs and hotspot geometry separately.
   Checkpoint a diagram only after its records are durable; reruns must tolerate
   partially written diagrams.
5. If downloading diagram media, use `ImgCacheClient.lookup` first, fetch source
   bytes through browser transport under a permit on a miss, then store through
   imgcache and retain the returned hash. Do not fetch placeholder assets or
   assume ordinary Python HTTP image downloads will work.
6. Defer individual part-detail enrichment and tuning catalogs. The diagram
   pages already provide a useful collection sample at much lower request cost.

**Proposed acceptance gate:** collect at least ten discovered diagrams per
sampled marque across three runs spread over 24 hours, including a browser
process restart with the same profile. Record cache hits separately from actual
live requests; cached output is not access-reliability evidence. Require all
sampled diagrams to yield valid identities and image references, explicitly
account for every failure, and compare stable membership fields rather than
time-dependent prices. Test the intended runtime/network separately before
claiming fleet readiness.

Recon artifacts for this session are in
`/home/daniel/.copilot/session-state/e2a89210-3e37-47fe-8918-07465f7e3b17/files/`:
`scuderia-recon.json` (107 sample membership rows, hotspot metadata, round
observations, and image hashes), `scuderia-parts.jsonl` (incremental-output shape
example), and `scuderia-catalog.png` (browser screenshot). No cookie values or
browser storage state are included. These session artifacts are local evidence,
not a repository-hosted dataset.

## Prototype implementation status

A bounded collection-only implementation is now in
[`scuderia/`](../../scuderia/README.md). Its captured-page parser, lossless JSONL
journal, cache/robots handling, and permit status reporting have focused tests.
No gyopart database schema or fleet configuration was changed.

The first independent local Chrome run required repeated operator validation and
was stopped; the full prototype has not yet demonstrated live collection.
It now requires an explicit CDP endpoint rather than implicitly opening fresh
local browsers. See
[the bootstrap issue](../issues/2026_10_13_scuderia_cold_browser_validation.md).
Recon success above must not be substituted for standalone runtime verification.

### Verified cluster Browserless runtime

The existing fleet's browser was identified from gyopart Helm values and the
live scrape-stack deployment, rather than inferred from a hostname:

| Surface | Verified finding |
|---|---|
| Production service | `browserless.scrape-stack.svc.cluster.local:3000`; no Browserless ingress |
| Dev fleet configuration | `browserless.scrapestack-dev.svc.cluster.local:3000` |
| Running package | `browserless-chrome` 1.61.1 |
| Running Chrome | 121.0.6167.85 |
| Headed connection | Successful through a temporary `kubectl port-forward`; `headless=false` |
| Documented solver command | `Browserless.solveCaptcha` rejected as an unknown CDP method on a blank page |
| Collector smoke | Fresh robots cache miss, then 30-second startup timeout; exit 1, zero output records |

The smoke used real webcache/imgcache/request-auth clients and did not open local
Chrome, retry bootstrap, or require operator validation. Its failure log did not
capture the final page title/status; the specific timeout cause remains
**unverified**. The collector is not yet a proven live scraper on this runtime.

[Current Browserless documentation](https://docs.browserless.io/baas/bot-detection/captchas)
describes managed-endpoint `solveCaptchas=true` and CDP CAPTCHA-solving events and
commands. Those APIs must not be attributed to the deployed legacy image.
No solver, paid endpoint, shared browser upgrade, or proxy change was enabled.
An automatic CAPTCHA solve is also not a guarantee that subsequent catalog
requests will pass the site's other checks.

The [user-supplied ZenRows article](https://www.zenrows.com/blog/bypass-cloudflare)
reinforces why copying HTTP headers alone is not equivalent to browser transport
and why returning HTTP 200 is not enough: the actual catalog must be validated.
Its vendor success claims are not measurements of Scuderia or this cluster.
It does not justify building a bespoke bypass, rotating proxies, or accessing an
undocumented origin. The next access experiment needs an explicitly selected
runtime with verified capabilities, not more manual-validation loops.
