# Cluster GitOps Plan: ArgoCD + cluster-gitops Repo

## Motivation

The scrape-stack Helm chart currently owns two cluster-level concerns:
- **CoreDNS** — serves ALL namespaces and apps, not just scrape-stack
- **Grafana Ingress + ServiceMonitor** — wires cluster Prometheus to scrape-stack

Separating these gives clean ownership:

```
cluster-gitops/   ← DNS, monitoring wiring, ArgoCD itself
scrape_stack/     ← scrape stack services only
gyopart/          ← gyopart services only
```

---

## Target Structure: `cluster-gitops` repo

```
cluster-gitops/
├── bootstrap/
│   └── argocd.yaml                    # ArgoCD Helm install instructions
├── infrastructure/
│   ├── coredns/
│   │   ├── configmap.yaml             # coredns-local-config — ALL zones
│   │   ├── deployment.yaml
│   │   └── service.yaml               # MetalLB LB at 192.168.0.61
│   └── monitoring/
│       ├── grafana-ingress.yaml       # Grafana at monitoring.local
│       └── service-monitors/
│           └── scrape-stack.yaml      # ServiceMonitor → otel-collector
└── apps/
    ├── scrape-stack.yaml              # ArgoCD Application CR
    └── gyopart.yaml                   # ArgoCD Application CR (future)
```

`infrastructure/coredns/configmap.yaml` becomes the single source of truth for all
DNS zones — no more `kubectl patch`. Every zone change is a PR to cluster-gitops.

---

## Phase A — Create `cluster-gitops` Repo

1. Init new git repo. Needs to be reachable by ArgoCD:
   - **GitHub private repo** (simplest, requires HTTPS PAT or SSH deploy key)
   - **Gitea on-cluster** (fully air-gapped, more infra)

2. Migrate CoreDNS to `infrastructure/coredns/`:
   - Extract live manifests (`kubectl get deploy,svc,cm -n scrape-stack -l app=coredns-local`)
   - Include `scrapestack-dev.local` zone (already patched in)
   - Add `argocd.local` zone while here

3. Migrate Grafana Ingress + ServiceMonitor to `infrastructure/monitoring/` as static YAML
   (no Helm templating needed — they're simple, static resources)

---

## Phase B — Clean Up Scrape-Stack Chart

**Remove** from `scrape_stack/helm/scrape-stack/`:
- `templates/dns-local.yaml` — entirely deleted
- `monitoring.grafanaIngress` block from `monitoring.yaml`
- `monitoring.serviceMonitor` block from `monitoring.yaml`
- `dnsLocal` section from `values.yaml` and `values-dev.yaml`

**Keep** in the chart:
- otel-collector (ConfigMap + Deployment + Service) — scrape-stack specific, stays

---

## Phase C — Deploy ArgoCD

- Install in `argocd` namespace via upstream Helm chart
- Expose at `argocd.local` via Traefik ingress (no new MetalLB IP — wildcard at .60 covers it)
- Add `argocd.local` zone to CoreDNS in `infrastructure/coredns/configmap.yaml`

Repo authentication options (decide based on where repos live):
- GitHub HTTPS + personal access token (simplest)
- SSH deploy key (cleaner for private repos)

---

## Phase D — Register Apps with ArgoCD

ArgoCD `Application` CRs in `cluster-gitops/apps/`. Example:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: scrape-stack
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/<you>/scrape_stack
    targetRevision: main
    path: helm/scrape-stack
    helm:
      valueFiles: [values.yaml]
  destination:
    server: https://kubernetes.default.svc
    namespace: scrape-stack
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Same pattern for `gyopart`. The cluster infrastructure itself is also registered as
ArgoCD apps — ArgoCD manages itself (app-of-apps pattern).

---

## Phase E — Secret Management

**Sealed Secrets** (Bitnami) recommended — no external secret store needed:
- `kubeseal` CLI encrypts a Secret on your workstation using the cluster's public key
- Encrypted `SealedSecret` YAML is safe to commit to Git
- Controller in cluster decrypts it back to a real Secret

Secrets to seal: Postgres credentials (scrape-stack + gyopart), API keys, ArgoCD repo creds.

---

## Critical: Migration Safety

ArgoCD must **not** auto-sync CoreDNS until `infrastructure/coredns/` exactly matches live.
Validate with `argocd app diff` before enabling auto-sync on any infra app. A bad sync on
CoreDNS takes down DNS for the entire cluster.

Order:
1. Create cluster-gitops, populate manifests
2. Install ArgoCD, register apps in **manual sync** mode
3. Run `argocd app diff` on each app — confirm zero drift
4. Enable auto-sync one app at a time, starting with non-critical apps

---

## What Doesn't Change

- IP allocation — no new MetalLB IPs (argocd.local uses Traefik wildcard at .60)
- CoreDNS pod location — stays in scrape-stack namespace at 192.168.0.61
- All running services — zero disruption, this is management layer only
