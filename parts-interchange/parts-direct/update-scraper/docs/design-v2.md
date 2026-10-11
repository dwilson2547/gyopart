# Update scraper v2 — design

Status (2026-10-11): **design, nothing built.** Design items are ⬜ planned; facts about the current
code and data are ✅ with where they were read.

**Goal (user, 2026-10-11):** stop maintaining `parts_interchange` through static datasets and bulk
loads. The update scraper creates and updates database rows as it scrapes, keeps every manufacturer
current, and fills the gaps the 2024 scrape left (first: 3,492 Mopar vehicles, see
`docs/issues/2026_10_11_mopar_scrape_cached_503_maintenance_pages.md` in the gyopart root).

**Approach:** evolve `update-scraper/`, not a rewrite. Keep the browser/stealth setup, the
vehicle-picker tree builder, `CachedParser`, and the webcache / imgcache / request-auth clients.
Replace the JSON state files with database writes and a work queue; add outage handling.

---

## 1. What exists

✅ read from the repo, 2026-10-11:

- `updater.py` — `RecentPartsDirectUpdater`. Playwright Chromium (local or browserless via CDP) with
  `playwright_stealth` and a pinned Chrome UA / `sec-ch-ua` to pass Cloudflare. Pages go through
  `WebCacheClient` (`max_cache_age_days`, default 30), images through `ImgCacheClient`, navigation
  permits through `RequestAuthClient`.
- State is three JSON files (`tree.json`, `parts.json`, `imgs.json`) loaded at start and re-saved
  during the run. **No database writes.**
- Coverage is `years_to_refresh` recent model years (default 7) from `recent_tree_builder.py`, merged
  into the existing tree by `tree_merge.py`. Older gaps (Mopar 2007, 2010–2019) are never revisited.
- `process_car_data()` opens **a new browser context per car** ("cookies isolated per car"), so every
  vehicle starts a fresh session and re-passes the Cloudflare check.
- Per car it fetches the categories page → each category's diagram page → each part page (skipped
  when `_should_refresh_part` says the part is fresh), saving diagram and part images on the way.
- `CachedParser.check_page()` rejects 403 / 429 / "No Internet" / "Page Not Found" — **not** the
  site's "503 Service Under Maintenance" page, the failure that emptied 3,492 Mopar vehicles. Its
  `search_text` line also has a precedence bug: when a `<title>` exists, the `<h1>` is never checked.
- `singlethreaded-scraper/src/utils/pg_writer.py` (May 2026 phase-2 plan) already has get-or-create
  and link helpers for every table plus `write_car_data()`. Only the old single-threaded `scraper.py`
  calls it. Its lookups are select-then-insert, cars are matched by `base_url`, parts by
  `part_number` alone.

✅ schema (`parts_interchange_common` 0.2.0 on PyPI, read 2026-10-11): unique constraints exist only
on lookup names (manufacturer, year, make, trim, engine, category). `image` has `imgcache_hash` /
`imgcache_bucket`. `scrape_run` exists. The schema is created with `create_all()`; there is no
Alembic setup for `parts_interchange`.

✅ prod data, checked 2026-10-11: no duplicates for any key proposed in §3.1. `car.car_id` (the site's
own id) has 8 duplicate groups within a manufacturer, so it is not usable as a key. One `part` row has
a NULL `part_number`.

---

## 2. Decisions

| Decision | Status |
|---|---|
| Evolve the existing updater; keep its scraping machinery | ✅ user agreed, 2026-10-11 |
| DB is the state; no JSON files, no bulk loads going forward | ✅ user, 2026-10-11 |
| One browser session per run, not per vehicle | ✅ user asked, 2026-10-11 |
| Keys are vehicle- and part-based, never site URLs/ids, so a manufacturer can move to a new site without duplicating rows | ⬜ proposed (user deferred to judgment) |
| A maintenance/5xx page stops the run as transient | ⬜ proposed (from the Mopar incident) |
| Runs scheduled by scrape-job-manager | ⬜ proposed |

---

## 3. Design

### 3.1 Keys and schema changes

Upserts need real unique keys. Added to `parts_interchange_common` (new version) and applied to prod
by migration (§3.9):

| Table | Unique key | Notes |
|---|---|---|
| `part` | `(manufacturer_id, part_number)` | OEM part numbers are site-independent. The NULL row is allowed by Postgres semantics. |
| `image` | `(manufacturer_id, name)` | |
| `car` | `(manufacturer_id, year_id, make_id, model_id, trim_id, engine_id)` | Replaces `pg_writer`'s `base_url` match. `base_url`, `car_id`, `vehicle_id` become updatable attributes. |
| `model` | `(make_id, select_value)` | Today guarded only in code. |
| `subcategory` | `(category_id, name)` | Today guarded only in code. |

New table **`scrape_target`** — the work queue and per-vehicle state, independent of `car` so a
vehicle can be known before it has data:

| Column | Purpose |
|---|---|
| `id`, `manufacturer_id` | |
| `year`, `make`, `model`, `trim`, `engine` | the site's select values (what the picker returned) |
| `page_url` | where to scrape it on the current site |
| `status` | `pending` · `done` · `no_catalog` · `failed` |
| `car_id` → `car.id` | set once a car row exists |
| `last_scraped_at`, `attempts`, `last_error` | |
| unique `(manufacturer_id, year, make, model, trim, engine)` | |

**A `car` row is only created when a scrape finds a catalogue.** The picker builds its lists from
`car` (✅ `gyopart-api/src/routers/vehicles.py`), so this keeps the rule established in the Mopar load:
no empty vehicles in the picker. A real page with no categories → `no_catalog`, no car row.

### 3.2 Seeding the queue

- **Mopar (`fiat`)** from `parts-direct-data/fiat/tree.json`: 739 vehicles → `done` and linked to their
  cars; 2,296 whose cached page is the real catalogue page with no categories → `no_catalog`; 3,492
  whose cached page is the maintenance page → `pending`.
- **Every other manufacturer:** one `done` row per existing `car`, `last_scraped_at` NULL (unknown,
  so they sort as most stale).
- **Discovery** (§3.3) adds new vehicles as `pending`.

### 3.3 The run

One run = one browser session working the queue until a time budget is spent:

0. **Check the VPN** (§3.8) — refuse to start if traffic would leave on the home IP.
1. Launch the browser and open **one** stealth context; load the homepage (passes Cloudflare). Recreate
   the context only on a challenge page, a 403, or a browser crash.
2. **Discovery**, at most once per `discovery_interval` (✅ 90 days per manufacturer, user 2026-10-11 —
   the vehicle list rarely changes): run the
   tree builder for `years_to_refresh` recent years and insert unknown vehicles as `pending`.
3. **Claim targets** in order: `pending`, then `failed` with backoff, then `done` older than
   `refresh_after` (✅ 180 days, user 2026-10-11), oldest first.
4. **Scrape one vehicle** with the existing per-car crawl (categories → diagrams → parts, through
   webcache/imgcache), collecting everything in memory.
5. **Write it in one transaction** (§3.5), then mark the target. Wait `spacing + jitter` (⬜ 20–60 s)
   before the next vehicle.
6. Stop when `SCRAPE_DEADLINE` is near, the queue is empty, or a stop condition fires (§3.4). Write a
   `scrape_run` row and the scrape-job-manager result payload.

**Stopping on time.** The operator only gates when runs *start*; a running pod is killed only at the
Scraper's `timeout` (the Job's `activeDeadlineSeconds`), and a kill counts as a failed run (Timeout →
one retry → toward suspension). So the updater stops itself: before claiming each vehicle it checks
`SCRAPE_DEADLINE` (⬜ injected by scrape-job-manager — the earlier of start + timeout − margin and the end
of the pool's current active-hours window) against a running estimate of time per vehicle, and if the
next vehicle wouldn't fit it commits, writes its result and exits 0. The `timeout` is then only a
backstop for a hung browser. A kill mid-vehicle loses that vehicle's work but nothing else (its
transaction rolls back).

### 3.4 Page validation and failure classes

`CachedParser.check_page()` / `check_cached_page()` learn the maintenance page (title "Service Under
Maintenance") and treat any 5xx response as failed; the precedence bug is fixed. A failed page is never
written to webcache, and a webcache hit that fails validation is deleted (already done today).

| Condition | Action | Exit |
|---|---|---|
| maintenance page, 5xx, Cloudflare challenge that doesn't clear | stop the run at once; the in-flight vehicle stays `pending` | 75 (operator retries later) |
| 403 / 429 | stop the run | 65 (blocked: no quick retry; counts toward suspension) |
| one vehicle's page fails to parse | target `failed` + `last_error`; continue | — |
| 5 consecutive vehicle failures | stop the run | 65 |
| `SCRAPE_DEADLINE` reached / queue empty | normal stop | 0 |

This is the rule the 2024 scrape lacked: an outage page cost seconds and a real vehicle hours, so the
scraper "finished" 3,277 vehicles in under five hours during one maintenance window.

### 3.5 Writing a vehicle

One transaction per vehicle, using `pg_writer`'s helpers rewritten as `INSERT … ON CONFLICT` on the
§3.1 keys:

1. Upsert year / make / model / trim / engine, then the `car` (update `base_url`, `car_id`,
   `vehicle_id`).
2. Upsert every `part` seen (title, description, msrp, etc. updated in place). Parts are shared across
   a manufacturer's cars and are never deleted.
3. Upsert `image` rows (with `imgcache_hash` / `imgcache_bucket` from imgcache) and `part_images`.
4. **Replace the car's link sets:** `car_parts` becomes exactly the parts on this scrape. Diagrams
   belong to one car (✅ the loader assigns diagram ids per car), so delete the car's diagrams and their
   `diagram_parts`, and insert the new ones.
5. Mark the `scrape_target` `done`, set `car_id` and `last_scraped_at`.

A crash mid-vehicle rolls back to the previous state of that car; re-running a vehicle is harmless.

### 3.6 Changing a manufacturer's site

Site-specific code is the tree builder (`recent_tree_builder.py`), the page parser (`CachedParser`) and
the config (base URL). Moving a manufacturer to a new site means a parser for the new site and new
`page_url`s in `scrape_target`. Because keys are vehicle- and part-based, the new site's scrapes update
the existing cars and parts in place instead of duplicating them. Select values differing between sites
(e.g. trim spelled differently) would create new lookup rows; that mapping is the cost of a site move,
handled when it happens.

### 3.7 Running under scrape-job-manager

- One shared manufacturer image (✅ user: one image for all manufacturer sites), built with the repo's
  docker compose (`scraper-parts-direct` ⬜), pinned by digest like the junkyard scrapers.
- One `ScrapeJob` per **manufacturer** (~22), never per vehicle: vehicles live in `scrape_target`, and a
  run works through as many as fit before its deadline; the next run resumes from the queue. A
  caught-up manufacturer finds nothing older than 180 days and exits in seconds with zero items.
  `params: {config: <name>}`; `SCRAPE_*` env per the operator's
  contract; result payload `{"items": vehicles_scraped, "new": …, "updated": …}`.
- **Several manufacturers at once** (✅ user ran 3–5 parts-direct scrapers concurrently in the past,
  each slow): every manufacturer is its own site, so the parts-direct `Scraper` gets
  `policy.concurrency: 4` (⬜) — up to four manufacturer jobs in parallel, one session per site.
  Per-site pacing stays with request-auth's per-domain permits. The operator's global
  `maxConcurrentRuns` (3 today, shared with the junkyard scrapers) would be raised to 6 (⬜) so day-long
  parts-direct runs don't starve the junkyard runs.
- `health.minItems: 0` — a run that only refreshed nothing because the site was down exits 75 instead,
  so zero items on exit 0 means "queue empty", which is fine.
- Browser: Chromium bundled in the image (⬜), so the VPN proxy can be set per launch (§3.8). The
  scrape-stack browserless (✅ `browserless` service in `scrapestack-dev`) would need the proxy as a
  server-wide launch flag instead.

### 3.8 Network: all site traffic through the VPN

✅ user requirement, 2026-10-11. The cluster's VPN is an HTTP proxy, Service
`nordvpn-proxy-entrypoint.vpn.svc.cluster.local:8118` (✅ `infra/cluster-config/vpn/deployment.yml`,
one replica — every concurrent job shares one exit IP).

- **Browser:** Playwright `launch(proxy={"server": "http://nordvpn-proxy-entrypoint.vpn.svc.cluster.local:8118"})`.
  With browserless over CDP the proxy is a browser launch flag instead, so a bundled Chromium is the
  simpler fit (resolves the §3.7 browser question in its favour).
- **`requests` calls** (✅ image downloads in `save_image`, the tree builder's picker AJAX): through
  `HTTP_PROXY`/`HTTPS_PROXY` env.
- **In-cluster services must bypass it:** webcache, imgcache and request-auth (gRPC honours
  `http_proxy` too) via `NO_PROXY=.svc,.svc.cluster.local,.cluster.local,localhost,127.0.0.1`.
- **Fail closed:** ✅ observed 2026-10-11 with the tunnel down — the proxy returns 500 for everything
  (its DNS servers are NordVPN's, reachable only through the tunnel). That is one failure mode, so each
  run also checks positively: the exit IP through the proxy must be a real IP and differ from the
  direct (home) IP; repeated every 50 vehicles, and the run exits 75 if it fails. (NordVPN's
  `vpn/check/full` endpoint now only answers `{"status": "deprecated"}`, ✅ 2026-10-11.)
- **Stuck tunnel:** ✅ 2026-10-11 the proxy sat on a dead server for an unknown time: OpenVPN soft-restarts
  against the same server forever, and the load-check cron ignores a server whose stats are empty.
  Deleting the pod picks a fresh recommended server. Durable fix tracked separately.

### 3.8a Cloudflare (✅ observed 2026-10-11 through the VPN)

- **Headless is blocked, headed passes.** Through the same exit IP and Chromium build, headless
  (headless shell and new-headless) got Cloudflare's block page or a challenge that never settled;
  headed Chromium loaded the site normally. The updater launches headed full Chromium; in the
  container it runs under Xvfb.
- **The vehicle-picker AJAX endpoints are stricter.** With `cf_clearance` already set, an XHR to
  `/ajax/vehicle-picker/makes/all` still got the challenge body ("Enable JavaScript and cookies to
  continue", 403). After one top-level navigation to that URL (which returned the JSON directly), the
  same XHR returned 200. Only discovery uses the picker; vehicle, category and part pages are plain page
  loads. So discovery warms up with that one navigation before its XHRs (⬜ when discovery is built).
- A Cloudflare block page stops the run as blocked (65); a challenge that never settles as transient
  (75).

### 3.8b Images

- A part page lists up to 8 product images in 3 sizes (✅ a 2026 page). Downloaded inline and one at a time
  they left the browser idle for minutes per part, so a vehicle's images are collected during the crawl
  and fetched 8 at a time after its pages.
- Image downloads take request-auth permits like page fetches, so they are paced, backed off and visible
  in its panel. The image CDNs need a larger pool than the default 1, configured in request-auth
  (✅ dev, 2026-10-11; ⬜ prod): `cdn-product-images.revolutionparts.io`,
  `cdn-illustrations.revolutionparts.io`, `s3.amazonaws.com`, `dz310nzuyimx0.cloudfront.net` — pool 8,
  base delay 200 ms.

### 3.9 Migrating the schema

`parts_interchange` has no migration history; prod holds real data, so changes go through Alembic
(✅ user preference for prod data). Add an Alembic environment next to `parts_interchange_common`,
stamp the current schema as the baseline, and write one revision for the §3.1 constraints and
`scrape_target`. Dev first, then prod.

---

## 4. Throughput

⚠ Estimate from the 2024 Mopar scrape: 739 vehicles took about 25 days (2024-08-22 → 2024-09-16), i.e.
roughly 50 minutes per vehicle including every part page. Later vehicles reuse part pages already
fetched (parts are shared across a manufacturer), so the real figure for the backlog should be lower —
unmeasured until the first runs.

At 50 minutes per vehicle, 3,492 vehicles ≈ 2,900 hours of scraping. Against the current
`junkyard-inventory`-style business hours (50 h/week) that is over a year. Options:

1. A **separate pool for parts-direct** with long active hours that avoid only the site's maintenance
   window (observed just after midnight, ✅ 2024 cache timestamps), e.g. 06:00–23:00 daily ≈ 119 h/week.
2. Allow concurrency 2 for this scraper (two sessions) — doubles load on the site.
3. Accept the long tail and refresh the most-searched makes first.

⬜ Recommendation: option 1 for hours, plus several manufacturers in parallel (§3.7). That doesn't speed
up one site's backlog (Mopar is one site, so one session), but it keeps the other manufacturers' 180-day
refresh moving at the same time. Measure real per-vehicle time in the first week; per-site speed is
then tuned through request-auth's permit rate for that domain rather than by adding sessions.

---

## 5. Phases

1. **Schema:** Alembic baseline + revision (keys, `scrape_target`); new `parts_interchange_common`
   version; apply to dev; seed the queue.
2. **Updater v2 core:** session reuse, page validation, queue claiming, transactional writer; run
   against dev for a handful of Mopar vehicles and compare with what the site shows.
3. **Under the operator:** `SCRAPE_DEADLINE` injection in scrape-job-manager; image, `scraper-parts-direct` compose service, `parts-direct` pool and a
   gyopart-dev ScrapeJob for Mopar; watch a week.
4. **Prod:** migrate prod, ScrapeJobs per manufacturer.

## 6. Open questions

- Pool hours and cadence for parts-direct (§4).
- Raising `maxConcurrentRuns` to 6 and parts-direct concurrency to 4 (§3.7).
- Whether `CachedParser` changes need to be shared with the single-threaded scraper (currently the
  updater imports it from `singlethreaded-scraper/src`), or the updater should own a copy.
