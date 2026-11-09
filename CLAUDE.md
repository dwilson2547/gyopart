# CLAUDE.md — gyopart

This file is loaded automatically. Read it before touching anything in this repo.

## Repo Structure

Monorepo at `workspace/gyopart/`. Services:
- `gyopart-api/` — FastAPI BFF, port 8200. Reads parts_interchange DB, proxies inventory_api.
- `gyopart-ui/` — React/Vite/Tailwind, port 5173/80. nginx proxy: `/v1/` → gyopart-api:8200.
- `junkyard-platform/` — Contains `inventory_api/` (port 8100), `admin_api/` (port 8300), `junkyard_common/`, `pipeline/`.
- `junkyard-inventory-scrapers/` — Scrapers.
- Junkyard schema migrations: `junkyard-platform/db/` (Alembic). Nothing applies them automatically: run
  `alembic upgrade head` from `/app/db` in the vin-resolver pod (dev first), before deploying code that needs them.
- `parts-interchange/` — Parts catalog data, loader, docs. Schema authority: `dwilson-parts-interchange-common` on PyPI.
- `helm/gyopart/` — Helm chart. `values.yaml` = shared defaults + prod (`gyopart.local`), `values-prod.yaml` = prod-only
  (the scraper fleet), `values-dev.yaml` = dev (`gyopart-dev.local`, namespace `gyopart-dev`). Helm merges
  `values.yaml` into every environment, so anything environment-specific (scraper jobs!) goes in that
  environment's file, never in `values.yaml`.

## Docker Images — ALWAYS use docker compose

**Never write raw `docker build` or `docker push` commands.** All images are built and pushed from the **gyopart repo root** using docker compose:

```bash
# Build and push a single service
docker compose build admin-api && docker compose push admin-api

# Build and push all
docker compose build && docker compose push
```

Images on Docker Hub are versioned, not `:latest`: the chart pins them in `helm/gyopart/values.yaml` (`images:`).
- `gyopart-api`, `gyopart-ui`, `inventory-api`: release versions (`3.0.x`, git tag `v3.0.x`), built from a clean
  checkout of the pushed commit with `GYOPART_TAG=<v> docker compose build <svc> && GYOPART_TAG=<v> docker compose push <svc>`.
- `admin-api`, `vin-resolver`: `sha-<commit>` tags.

A new version goes into `values-dev.yaml` (`images:` override) first and moves to `values.yaml` on `main` once
proven in dev. Pushing `:latest` changes nothing that's deployed.

**Scraper images** (`scraper-*` services) are the exception to "restart after push": they are pinned
by digest in `helm/gyopart/values-dev.yaml` and `values-prod.yaml`. After pushing, run
`scripts/pin-scraper-images.sh <values file>` for each and commit; scrape-job-manager picks up the new digest on its next run.

After pushing, restart the deployment to pull the new image:
```bash
kubectl rollout restart deployment/<name> -n gyopart-dev
```

If pods are still running old images after a push, check `imagePullPolicy` in the relevant values file before assuming a node cache problem.

## Kubernetes / ArgoCD Deployment — ALWAYS use git push

**Never `kubectl apply` for anything managed by ArgoCD.** Changes deploy via:

```bash
git add ... && git commit -m "..." && git push
```

ArgoCD auto-syncs (`selfHeal: true`, `prune: true`) and applies the change.

**Exceptions — manual kubectl only:**
- Secrets (never committed): `kubectl apply -f secret.yml`
- **ArgoCD Application manifests** (`cluster_config/argocd/gyopart.yaml`, `gyopart-dev.yaml`): git push alone is NOT enough. These must ALSO be applied manually every time they change:
  ```bash
  kubectl apply -f /home/daniel/documents/workspace/cluster_config/argocd/gyopart-dev.yaml
  kubectl apply -f /home/daniel/documents/workspace/cluster_config/argocd/gyopart.yaml
  ```
  ArgoCD does not manage its own Application CRs (no app-of-apps). If you only push and don't apply, the cluster still has the old config.

ArgoCD apps:
- `gyopart` → tracks `main` branch, namespace `gyopart`
- `gyopart-dev` → tracks `dev` branch, namespace `gyopart-dev`

## cluster_config Repo

Infrastructure (DNS, monitoring, postgres, ArgoCD, ai-services, etc.) lives at `workspace/cluster_config/`. Same GitOps rule: commit + push to deploy.

**DNS changes** (`cluster_config/dns/dns.yaml`):
- Edit the CoreDNS ConfigMap zone file, bump the serial, commit and push.
- CoreDNS with the `file` plugin does NOT hot-reload ConfigMaps automatically — after ArgoCD syncs, run:
  ```bash
  kubectl rollout restart deployment/coredns-local -n dns
  ```

## Two-Database System

- `junkyard_inventory` — scraper data. Schema authority: `dwilson-junkyard-common` on PyPI (`junkyard_common/models.py`). Used by inventory_api, admin_api, pipeline.
- `parts_interchange` — parts catalog. Schema authority: `dwilson-parts-interchange-common` on PyPI. Used by gyopart-api.
- Prod postgres: `postgres.postgres.svc.cluster.local`
- Dev postgres: `postgres-dev.postgres.svc.cluster.local`

## Secrets

Never committed. Pre-provisioned with kubectl. Example templates in `helm/gyopart/example-secrets/`.
- `junkyard-credentials` — JUNKYARD_USER, JUNKYARD_PASSWORD (ADMIN_API_KEY is unused: the admin signs in through authentik)
- `gyopart-admin-oidc` — OIDC_CLIENT_ID, OIDC_CLIENT_SECRET (admin sign-in; same value as `authentik-gyopart-admin-oidc` in the authentik namespace)
- `parts-interchange-credentials` — PARTS_USER, PARTS_PASSWORD

## Ingresses

- `gyopart.local` → gyopart-ui:80
- `gyopart.danwils.com` → gyopart-ui:80, **public** (prod only, `publicIngress` in `values-prod.yaml`; anonymous, read-only; `/v1/vin/` rate-limited).
- `gyopart-admin.danwils.com` → admin-api:8300 (prod) and `gyopart-admin-dev.danwils.com` (dev), **public behind
  authentik sign-in** (group `gyopart-admin`; `adminAuth` + `adminPublicIngress` in values). With sign-in on, the LAN
  `admin.*` hosts redirect page loads to the public host. Its MCP server (discrepancy fixes) is at `<that host>/mcp`,
  OAuth sign-in from the client (`junkyard-platform/admin_api/mcp`).
- `api.gyopart.local` → gyopart-api:8200
- `admin.gyopart.local` → admin-api:8300
- `inventory.gyopart.local` → inventory-api:8100
- Dev equivalents use `gyopart-dev.local` subdomain pattern
