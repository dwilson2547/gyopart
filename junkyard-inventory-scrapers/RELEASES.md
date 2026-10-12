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
| `pull_a_part_scraper/` | `pull_a_part` | [ ] | [ ] | |
| `speedwayap/` | `speedway_ap` | [ ] | [ ] | |
| `arizonaautoparts/` | `arizona_auto_parts` | [ ] | [ ] | |
| `las-parts/` | `las_parts` | [ ] | [ ] | |
| `strickerautoparts/` | `stricker_auto_parts` | [ ] | [ ] | |
| `midwayupull/` | `midway_upull` | [ ] | [ ] | |
| `centralfloridapickandpay/` | `central_florida_pick_and_pay` | [ ] | [ ] | |
| `picknpullsa/` | `picknpullsa` | [ ] | [ ] | |
| `budgetupullit/` | `budget_upullit` | [ ] | [ ] | |
| `ipullupull/` | `ipullupull` | [ ] | [ ] | |
| `utpap/` | `utpap` | [ ] | [ ] | |
| `wrenchapart/` | `wrenchapart` | [ ] | [ ] | |
| `u-pull-n-save/` | `u_pull_n_save` | [ ] | [ ] | |
| `fenixupull/` | `fenix_upull` | [ ] | [ ] | |
| `tearapart/` | `tear_a_part` | [ ] | [ ] | |
| `pull-n-save/` | `pull_n_save` | [ ] | [ ] | |
| `wegotused/` | `wegotused` | [ ] | [ ] | |
| `chesterfieldauto/` | `chesterfield_auto` | [ ] | [ ] | |
| `pyp/` | `pyp` | [ ] | [ ] | |
| `usedautopartsfl/` | `used_auto_parts_fl` | [ ] | [ ] | |

Recon only, no scraper (see `SCRAPERS.md` § Sites Excluded): `baughmansupullit`, `coloradoautoandparts`,
`indyupullit`, `jacksusedautoparts`, `jksalvageco`, `mcdonoughautoparts`, `sturtevantauto`.
