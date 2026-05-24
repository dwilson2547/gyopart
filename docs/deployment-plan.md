# Gyopart Dev-to-Prod Deployment Plan

## Architecture

```
scrapers (19) → junkyard-inventory DB → pipeline → car_id + lat/lng resolved on vehicles
parts-loader-v2 (local) → parts-interchange DB → gyopart-api → gyopart-ui
                                                      └→ inventory_api (Haversine junkyard search)
                                                      └→ admin_api (discrepancy UI + LLM suggester)
```

---

## IP Allocation

| IP | Service |
|----|---------|
| .60 | Traefik ingress (existing) |
| .61 | Single CoreDNS pod — all zones (existing, updated) |
| .62 | prod `request-auth-server` gRPC LoadBalancer (existing) |
| .63 | dev `request-auth-server` gRPC LoadBalancer (new) |

All DNS — prod scrapestack, dev scrapestack, gyopart dev, gyopart prod — served from the single
existing CoreDNS pod at .61. Update its ConfigMap (`coredns-local-config` in `scrape-stack` ns)
to add new zone blocks. No new DNS pods ever.

**Zones to add:**
- `scrapestack-dev.local` — wildcard → .60; `request-auth-server` → .63
- `gyopart-dev.local` — wildcard → .60
- `gyopart.local` — wildcard → .60 (reserved for prod)

---

## Docker Images

| Image | Source dir | Notes |
|-------|-----------|-------|
| `dwilson2547/inventory-api` | `junkyard-platform/inventory_api/` | `JUNKYARD_DATABASE_URL` |
| `dwilson2547/admin-api` | `junkyard-platform/admin_api/` | `JUNKYARD_DATABASE_URL`, HF env vars |
| `dwilson2547/pipeline` | `junkyard-platform/pipeline/` | both DB URLs |
| `dwilson2547/junkyard-migrator` | `junkyard-platform/db/` | runs `alembic upgrade head`; init Job |
| `dwilson2547/scraper-base` | `junkyard-inventory-scrapers/` | unified image, Playwright inside |
| `dwilson2547/gyopart-api` | `gyopart-api/` | `PARTS_DATABASE_URL`, `INVENTORY_API_URL` |
| `dwilson2547/gyopart-ui` | `gyopart-ui/` | node:20 build → nginx:alpine |

**Parts loader is not an image** — run locally via `kubectl port-forward` against the dev Postgres.

---

## DB Initialization

- **Junkyard inventory DB**: Alembic migrations in `junkyard-platform/db/alembic/versions/`.
  Deploy as a Kubernetes Job (`junkyard-migrator`) that completes before API deployments start.
  Migrations: `0001_initial_junkyard_schema`, `0002_vin_cache`.

- **Parts interchange DB**: `parts-loader-v2/schema.sql`. Run as a Job (`parts-schema-init`)
  before running parts-loader locally. Then run loader locally:
  ```bash
  kubectl port-forward -n gyopart-dev svc/postgres-parts 5432:5432
  # in parts-loader-v2: run_generate.sh then run_load.sh against localhost:5432
  ```

---

## Geocoding

Pipeline geocodes Location rows (zip → lat/lng) using `uszipcode` — already a dependency of
`inventory_api`, no new service needed. Zip centroid accuracy is acceptable for radius search.
Nominatim/OSM is a future option if address-level precision becomes necessary.

---

## Admin API LLM

`llm_suggester.py` currently uses the Anthropic SDK. Swap for HuggingFace at implementation time.
Two options (decide then):
- **HF Inference API** (cloud): `huggingface_hub.InferenceClient`, free tier, no infra
- **Ollama on cluster**: local model (Llama 3.1 8B / Mistral 7B), fully air-gapped

Both work with the existing prompt structure (expects JSON output). No tool-calling needed —
the suggester already queries both DBs to build context before calling the LLM.

---

## Phase 0 — Helm Validation + Dockerfiles

1. `helm template scrape-stack ./scrape_stack/helm/scrape-stack/ -n scrape-stack` — diff against
   live manifests to confirm chart matches what's deployed.
2. Write Dockerfiles for all images in the table above.
3. Write `values-dev.yaml` for the scrapestack chart (dev namespace, dev domain, gRPC at .63).

---

## Phase 1 — Dev Scrapestack

Deploy `scrapestack-dev` namespace via existing Helm chart + `values-dev.yaml`.
Update prod CoreDNS ConfigMap to add `scrapestack-dev.local` zone (wildcard → .60,
`request-auth-server` → .63).

---

## Phase 2 — Parts Interchange Load

Deploy dev Postgres for parts data. Verify `parts-loader-v2` against
`~/nfs-share/parts-direct-data` (20 manufacturer dirs):
1. Run generate on one manufacturer (e.g. `honda/`) — inspect CSVs
2. Run load against dev Postgres — verify row counts + FK integrity
3. Full load all 20 manufacturers

---

## Phase 3 — Gyopart Services

Deploy `gyopart-dev` namespace. Order of operations:
1. Postgres StatefulSets (inventory + parts)
2. `junkyard-migrator` Job (Alembic migrations)
3. `parts-schema-init` Job (schema.sql)
4. `inventory-api`, `admin-api` Deployments
5. `gyopart-api`, `gyopart-ui` Deployments
6. Pipeline CronJob
7. 19 scraper CronJobs

**gyopart-ui audit:** Build locally (`npm run build`) and fix any TypeScript/wiring issues before
writing the Helm template. Components exist but API wiring needs verification.

---

## Phase 4 — Scraper Schedule (UTC)

| Cron | Scrapers | Rationale |
|------|----------|-----------|
| `0 2 * * *` | `ipullupull`, `utpap` | CSV/XML feed, trivial |
| `0 3 * * *` | `wrenchapart` | flat JSON API, fast |
| `30 3 * * *` | `central_florida_pick_and_pay`, `picknpullsa` | single GET SSR |
| `0 4 * * *` | `parts_galore`, `usedautopartsfl` | single GET / Google Sheets |
| `30 4 * * *` | `budget_upullit` | 39-make enumerate |
| `0 5 * * *` | `wegotused` | stop-on-known, fast after first run |
| `30 5 * * *` | `tearapart` | nonce + 2 stores |
| `0 6 * * *` | `pull_n_save` | 8 stores × makes |
| `30 6 * * *` | `pull_a_part_scraper` | multi-phase, largest single scraper |
| `0 7 * * *` | `pic_n_pull` | location-scoped zip search |
| `0 8 * * *` | `u_pull_n_save` | year × make × model matrix |
| `0 9 * * *` | `fenixupull` | ~1,150 requests, 4 locations |
| `30 9 * * *` | `chesterfieldauto` | ASP.NET token + make enumerate |
| `0 10 * * *` | `speedwayap`, `strickerautoparts` | URG SSR, fast |
| `30 10 * * *` | `arizonaautoparts`, `las_parts` | URG SSR, multi-location |
| `0 11 * * *` | `midwayupull` | URG admin-ajax variant, 2 locations |
| `30 11 * * *` | `ryans_pic_a_part` | Playwright intercept, 1 location |
| `0 12 * * *` | `pyp` | Playwright + 62 locations (slowest) |
| `30 14 * * *` | **pipeline** | runs after scrape window closes |

---

## Phase 5 — E2E Smoke Test

1. Manually trigger 2–3 fast scrapers (ipullupull, wrenchapart, central_florida_pick_and_pay)
2. Trigger pipeline — verify VINs decode, vehicles get `car_id` + lat/lng assigned
3. Open `gyopart-dev.local` — pick year/make/model/part, enter zip, verify results
4. Check `admin.gyopart-dev.local` — verify discrepancy queue shows unresolved records

---

## Phase 6 — Prod Promotion

Tag images with semver, write `values-prod.yaml` for both charts, promote to `scrape-stack`
and `gyopart` namespaces, update CoreDNS `gyopart.local` to point at prod services.

---

## Future / Deferred

- **Scraper monitoring**: no visibility into failed runs or stale scrapers — needs a monitoring
  strategy (could use existing Grafana in `monitoring.local`, ScrapeRun table as source of truth)
- **Nominatim/OSM**: address-level geocoding if zip centroid proves too coarse for radius search
- **HF model selection**: finalize Inference API vs Ollama for admin_api LLM suggester
