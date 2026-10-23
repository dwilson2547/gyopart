# Scraper release status

Where each yard scraper runs under scrape-job-manager. Tick **Dev** when a run has succeeded in
`gyopart-dev` (`helm/gyopart/values-dev.yaml`) and the rows were checked in the dev DB; tick **Prod**
when the job is in `helm/gyopart/values-prod.yaml` and deployed from `main`, and a prod run has succeeded. Once a scraper is in prod its dev job is
`suspend: true` (no duplicate traffic); run-now it in dev to test a change first. Getting a scraper ready
to run under the operator (contract, image, schedule) is in `README.md` § Running under
scrape-job-manager.

| Scraper | Source | Dev | Prod | Notes |
|---------|--------|:---:|:----:|-------|
| `us_auto_parts_sterling_heights/` | `us_auto_supply` | [x] | [x] | Prod pool `junkyard-daily` (feed refreshes ~01:30). First runs 2026-10-12, dev and prod: 1,092 vehicles each |
| `parts-galore/` | `parts_galore` | [x] | [x] | First prod run 2026-10-12: 1,063 vehicles |
| `pic-n-pull/` | `pic_n_pull` | [x] | [x] | One job loops every location. First prod run 2026-10-12: 12,725 vehicles |
| `ryans_pic_a_part/` | `ryans_pic_a_part` | [x] | [x] | Recent-arrivals feed: drop check off. First prod run 2026-10-12: 17 vehicles |
| `pull_a_part_scraper/` | `pull_a_part` | [x] | [ ] | Detail phase stops at `SCRAPE_DEADLINE` (dev verified with a 20 m timeout); prod timeout 4 h. Dev run 2026-10-13: 37,826 vehicles. In prod; first run in progress 2026-10-13 |
| `speedwayap/` | `speedway_ap` | [x] | [ ] | Incremental (latest-arrivals): drop check off, 3 h for the uncached first crawl. Dev 2026-10-13: 10,246. In prod; first run in progress 2026-10-13 |
| `arizonaautoparts/` | `arizona_auto_parts` | [x] | [x] | Incremental: drop check off, 3 h timeout. First prod run 2026-10-13: 4,257 |
| `las-parts/` | `las_parts` | [x] | [x] | Incremental: drop check off, 3 h timeout. First prod run 2026-10-13: 3,619 |
| `strickerautoparts/` | `stricker_auto_parts` | [x] | [ ] | Incremental: drop check off, 3 h timeout. Dev 2026-10-13: 25,124. In prod; first run in progress 2026-10-13 |
| `midwayupull/` | `midway_upull` | [x] | [ ] | Server stalls on some pages: requests retry (`with_retries`), 3 h timeout. Dev 2026-10-14: 1,870. First complete prod run 2026-10-23: 2,779 across 3 yards, 3,906 pages in 2 h 36 m at 1 s pacing (5 h timeout). Tulsa (`OO95`) added 2026-10-23, crawled per yard with `?id=` |
| `centralfloridapickandpay/` | `central_florida_pick_and_pay` | [x] | [x] | Needs the honest UA (browser UA without a browser TLS fingerprint → 403). First prod run 2026-10-13: 1,287 |
| `picknpullsa/` | `picknpullsa` | [x] | [x] | Paged `/inventory?page=N`; stops on a repeated page. First prod run 2026-10-13: 4,222 |
| `budgetupullit/` | `budget_upullit` | [x] | [x] | Honest UA, as above. Drop check off. First prod run 2026-10-13: 1,547 |
| `ipullupull/` | `ipullupull` | [x] | [x] | First prod run 2026-10-13: 4,069 |
| `utpap/` | `utpap` | [x] | [x] | First prod run 2026-10-13: 1,806 |
| `wrenchapart/` | `wrenchapart` | [x] | [x] | First prod run 2026-10-13: 11,139 |
| `u-pull-n-save/` | `u_pull_n_save` | [x] | [ ] | Year×make×model matrix (~20k searches); lists and empty results reused for a week, 8 h timeout for the first sweep. Dev 2026-10-14: 1,148. In prod; first run in progress 2026-10-14 |
| `fenixupull/` | `fenix_upull` | [x] | [x] | Full crawl per location via the `fnx_location` cookie; 4 h timeout. First prod run 2026-10-13: 5,351 |
| `tearapart/` | `tear_a_part` | [x] | [x] | First prod run 2026-10-13: 1,624 |
| `pull-n-save/` | `pull_n_save` | [x] | [x] | Honest UA, as above; yard ZIPs set in `_STORE_DEFS`; 3 h timeout. First prod run 2026-10-13: 11,402 |
| `wegotused/` | `wegotused` | [x] | [x] | Sucuri JS challenge passed once per run in headless Chromium (Playwright image), then requests with its cookie + User-Agent. Incremental: drop check off. First prod run 2026-10-15: 4,092 |
| `chesterfieldauto/` | `chesterfield_auto` | [x] | [ ] | Search needs make + model since 2026-10 (~2,100 searches); model lists and empty results reused for a week. Dev 2026-10-15: 2,214. In prod; first run in progress 2026-10-15 |
| `pyp/` | `pyp` | [ ] | [ ] | Parked: Cloudflare serves headless Chromium one page, then challenges every request after it (inventory endpoint and `?page=N` alike). No route without disguising the browser; not pursued |
| `usedautopartsfl/` | `used_auto_parts_fl` | [x] | [x] | First prod run 2026-10-13: 457 |

Recon only, no scraper (see `SCRAPERS.md` § Sites Excluded): `baughmansupullit`, `coloradoautoandparts`,
`indyupullit`, `jacksusedautoparts`, `jksalvageco`, `mcdonoughautoparts`, `sturtevantauto`.
