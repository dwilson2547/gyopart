# TODO

Backlog imported from the retired todo store, 2026-07-06.

## Urgent

- [ ] **Build a parser for Ducati parts PDFs** — Create a Ducati parts parser that works on scanned or image-based PDFs because the current parser only handles text-based documents.

## High

- [x] **Add DB write path to parts-direct updater** — Wire parts_interchange DB writes into updater.py so scraped data lands in Postgres in one pass. Covers Vehicle, Part, diagram, and fitment records. Architecture decision: scraper writes cache + DB together, no separate loader for new runs. Related: context-store: gyopart/issues/parts-direct-picker-ajax-get-csrf, notes #16 (phase status), master plan at parts-interchange/docs/superpowers/plans/2026-05-17-parts-interchange-master-plan.md. — done 2026-10-11 as update scraper v2 (`parts-interchange/parts-direct/update-scraper/docs/design-v2.md`): writes Postgres directly, work queue, no loader.
- [x] **Validate update-scraper fix against Mopar sites** — Figure out whether the update-scraper fix we made also works correctly on the Mopar sites before rolling it out more broadly. — done 2026-10-11: v2 live-tested on Mopar (dev), now running in prod.
- [ ] **Regression-test Lexus update-scraper fix across other makes** — Make sure the Lexus-specific update-scraper fix did not break the updater flow for the other makes. Cross-check against the broader updater work as needed.
- [ ] **Add monitoring coverage for gyopart** — Review the current gyopart monitoring gap and add the missing observability pieces so the production stack is no longer under-monitored.
- [x] **Add junkyard inventory scraper CronJobs to Helm** — Set up the CronJobs for the junkyard inventory scrapers in Kubernetes and add the deployment wiring to the Helm chart. — superseded 2026-10-11: scrape-job-manager runs them (3 yards in gyopart-dev); prod move still open below.
- [ ] **Build a motorcycle parts interchange system** — Create the parts interchange system for the motorcycle parts data, including the core modeling and workflow decisions.
- [ ] **Map Ducati superseded part numbers in the scraper** — Write a Ducati scraper flow that detects chained part-number replacements and records mappings so superseded part numbers resolve as the same interchange part.

## Medium

- [ ] **Find a parts source for pre-2017 Alfa Romeo** — parts.alfaonlineparts.com (onboarded 2026-10-13 as parts-direct config `alfa`) has OEM catalogues only from 2017 (Giulia, Stelvio, Tonale, 2019 4C; varies by trim); the 1985–95 cars, the 8C and the 2015 4C redirect to aftermarket. Mopar's picker lists Alfa too but carries only maintenance items.
- [ ] **Bring the held-back parts-direct sites back** — audi/acura/porsche moved to oempartsonline.com (picker 403, different vehicle URLs), vw redirects to a dealer site, mazda's Cloudflare never clears from the VPN, suzuki has an expired certificate. Details: update-scraper `docs/design-v2.md` §0.
- [x] **Move the junkyard scrapers to prod** — done 2026-10-12: us-auto-supply (daily), parts-galore, pic-n-pull, ryans in prod; dev copies suspended. Remaining yards tracked in `junkyard-inventory-scrapers/RELEASES.md`.
- [ ] **Ryan's Pic-a-Part barely matches** — 1 of 17 vehicles resolves to a catalogue car (prod, 2026-10-12); the other yards are 80–87%. Check what the feed gives (VINs? model names?) and the decodes.
- [ ] **Requeue unmatched vehicles as the catalogue fills** — ~13% of yard vehicles have no candidates, mostly model years the catalogue hasn't scraped yet (Mopar stops ~2009). `python -m pipeline.worker --requeue discrepancy` re-resolves them but nothing runs it; schedule it (e.g. after parts-direct runs) or trigger on new cars.
- [ ] **Calgary Pic-n-Pull doesn't geocode** — uszipcode has no Canadian postcodes, so the location has no lat/lng and never appears in radius search.
- [ ] **pyp (LKQ Pick Your Part, 62 yards) is parked** — Cloudflare lets headless Chromium load one page and challenges everything after it; a headed browser stalls on the challenge. Getting past it would mean disguising the scraper, which we decided against (2026-10-15). Revisit only if LKQ offers a feed or the protection changes.
- [ ] **U-Pull and Save misses cars named off-catalogue** — search matches the car's own model label, and the matrix comes from the site's Hollander catalogue; a 1994 Olds labelled "OLDS 88" (catalogue: "88 Royale") is never searched. Size the gap (compare the recent feed against crawl results) before deciding on a fix.
- [ ] **Midway U-Pull: add the Tulsa yard** — cards now show "Tulsa U-Pull"; it maps to the Unknown location until its address is added to `_LOCATION_DEFS`.
- [ ] **IIS Pro model pages may cap at 30 cards** — speedway/stricker/las/arizona crawl `/parts/{MAKE}/{MODEL}/`; if a model page truncates at 30 vehicles without paging, popular models are undercounted. Compare a big model's page count against the site's own total.
- [ ] **Parts-direct crawl delay on the other 13 sites** — bmw/mitsubishi/volvo dropped from robots.txt's 10s to 2s (`base_delay_ms=2000` in request-auth) on 2026-10-12 as a trial; if they behave, apply to the rest.
- [ ] **Image sweep job for parts-direct** — drain `image.saved = false` (images in flight when a run stopped, CDN failures, the 2024 backlog) on its own schedule. Agreed 2026-10-11, design-v2 §6.
- [ ] **Decide refresh for brand-new models** — with refresh off, sparse new models (2026 Mini Cooper: accessories only) aren't revisited; refresh current/next model year sooner? design-v2 §6.

- [x] **Deploy gyopart production stack** — Bring up the production gyopart deployment using the existing Helm and cluster patterns from the gyopart stack. — done 2026-10-11: Argo app `gyopart` (main, values.yaml + values-prod.yaml), gyopart.local.
- [ ] **Expose VinCache data in the gyopart admin experience** — Extend the admin-facing experience to make VinCache data inspectable, either in the current admin interface or wherever it fits best.
- [ ] **Extend gyopart API and UI functionality** — Review the current gyopart API and UI end-to-end and add the next round of missing functionality and quality-of-life improvements.
- [ ] **Explore a standalone parts-interchange interface on gyopart data** — Consider building a separate parts-interchange API/UI that uses the same underlying data as gyopart so workflows can be compared and potentially swapped later.
- [x] **Deploy update-scraper to Helm after DB-write stabilization** — Once update-scraper bugs are fixed and it writes directly to the database reliably, add Helm deployments for each make. — done 2026-10-11: one ScrapeJob per site under scrape-job-manager (16 sites, design-v2 §0).
- [ ] **Clean up junk code in the gyopart repo** — Go through the gyopart repository and remove stale or junk code paths so the tree is easier to reason about.
- [ ] **Run motorcycle scrapers in Kubernetes with admin services** — Update the motorcycle scrapers to run in Kubernetes and add the associated admin/API-style services needed to operate them.
- [ ] **Build a framework for general document scrapers** — Create a reusable scraper system for document-centric scrapers such as the Ducati owners manual scraper.
- [ ] **Explore local LLM rule generation for gyopart admin-api** — Experiment with a local LLM connected to the gyopart admin-api to automatically create rules that resolve mapping discrepancies.
- [ ] **Evaluate RockAuto-style external parts reference scraping** — Consider scraping an external parts reference such as RockAuto to find parts interchangeable across manufacturers, but first collapse vehicles into distinct canonical car configurations so equivalent generations/configs are only scraped once instead of re-querying every model year.

## Low

- [ ] **Catalogue gaps: check the requeued cars landed (check 2026-10-16)** — the 2010 Impala had diagrams but no parts because the original 2023–24 scrape marked it `done` with an empty parts list (`has_parts: 0` in `gm/tree.json`), not a CSV/load fault. Seeding `scrape_target` from `car` then marked every car `done`, so nothing re-checked them. On 2026-10-15 these were set to `pending` in prod:
  - 52 partial scrapes: car ids 21846–21895 (2010 Chevrolet Camaro → Malibu, 49 with zero parts plus the Camaro LS at 131) and 38080–38081 (2022 Subaru BRZ, ~1.2 parts/diagram vs ~7 normal).
  - 2,629 cars with neither diagrams nor parts, all model years ≤2024, across every manufacturer but Fiat (1,068 are 2023–24, likely too new at scrape time; 844 are ≤2020).
  Throughput was the limit (GM ~7 vehicles/day, new 2025–26 vehicles queue first; 821 of the requeued belong to the held-back sites below). Since 2026-10-15 the updater keeps starting vehicles until 5 min before SCRAPE_DEADLINE (it used to stop when an average vehicle no longer fit, idling 30–45% of slow sites' windows) and `car_diagrams(diagram_id)` / `diagram_parts(part_id)` are indexed (re-scrapes deleting old diagrams scanned 8.7M rows per diagram). Check the runs end "deadline reached mid-vehicle: released" near the 3 h mark.
  Check: the 2010 Impala (car 21889) shows parts; count of `pending` targets left per manufacturer; how many came back `no_catalog` vs `done` with parts; `failed` targets and their `last_error`.

- [ ] **Indexes into `parts_interchange_common`** — `ix_diagram_parts_part_id` and `ix_car_diagrams_diagram_id` were created by hand on prod 2026-10-15 (CONCURRENTLY); add them to the schema package (new PyPI version) and to dev. Was: **Index `diagram_parts.part_id`** — the PK is (diagram_id, part_id), so "which diagrams is this part on" scans ~135M rows (~8 s). gyopart-api works around it by going through car_parts → car_diagrams (0.7–1.5 s without a car). Needs the index in `parts_interchange_common` (new PyPI version) and `CREATE INDEX CONCURRENTLY` on dev + prod.

- [ ] **Pre-existing admin-api test failure** — `test_list_discrepancies_requires_auth` fails (seen 2026-10-12, unrelated to the VIN resolver work).

## Unprioritized (imported from workman drafts, 2026-07-06)

- [ ] **Migrating LLM suggester from Anthropic to HuggingFace** — admin_api/llm_suggester.py currently uses Anthropic SDK. Swap for HuggingFace at implementation time. Two options: HF Inference API (cloud, free tier, no infra) or Ollama on cluster (Llama 3.1 8B / Mistral 7B, air-gapped). Prompt structure stays the same (expects JSON output). Both DBs queried to build context before calling LLM.
- [ ] **Adding Nominatim/OSM address-level geocoding** — Current geocoding uses uszipcode (zip centroid). Add Nominatim/OSM as fallback for address-level precision if zip centroid proves too coarse for radius search. Location.address field already stored by scrapers.
- [ ] **Implementing cluster GitOps repo** — Extract CoreDNS and monitoring concerns from scrape-stack Helm chart into a separate cluster-gitops repo. Structure: bootstrap/, infrastructure/coredns/, infrastructure/monitoring/, apps/. SealedSecrets for committing encrypted secrets. ArgoCD manages itself (app-of-apps). Zero-disruption migration: validate with argocd app diff before enabling auto-sync on infra apps.
- [ ] **Set up Aistor bucket and IAM credentials for gyopart** — Create a dedicated bucket (e.g. gyopart-images) on the Aistor S3-compatible instance. Create an IAM user/key pair with read-write access for the migration script, and a separate read-only key for gyopart-api. Store the read-only credentials as a Kubernetes secret in the gyopart-dev namespace.
- [ ] **Write image migration script to copy from source URLs to Aistor bucket** — One-off script that reads all Image records from the parts-interchange database (bucket_path, url columns), downloads each image from the original URL, and uploads it to the Aistor bucket under the same bucket_path key. Should be idempotent (skip if key already exists), log progress, and report failed downloads. Estimated ~50k images based on scrape volume.
- [ ] **Update gyopart-api to serve image URLs from Aistor bucket** — Add AISTOR_BASE_URL config variable to gyopart-api. In DiagramDetailOut and any schema that exposes image_url, construct the URL as {AISTOR_BASE_URL}/{bucket_path} instead of the raw url column from the DB. Fall back to the original url column if bucket_path is null so the API stays functional before migration completes.
- [ ] **Verify image rendering in gyopart UI after migration** — After migration and API update are deployed, spot-check diagrams and part images in the gyopart UI. Confirm in browser devtools that no requests go to original source domains. Run Playwright tests to verify diagram view renders an image and update any URL assertions to match the Aistor domain pattern.
