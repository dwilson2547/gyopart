---
title: Gyopart — Docker images and Helm/ArgoCD deployment
date: 2026-05-31
tags: k8s, helm, argocd, docker
---

Four images on Docker Hub: dwilson2547/gyopart-api:latest (port 8200), dwilson2547/gyopart-ui:latest (port 80), dwilson2547/inventory-api:latest (port 8100), dwilson2547/admin-api:latest (port 8300). Build+push all at once via docker-compose.yml at gyopart/ root. Helm chart at gyopart/helm/gyopart/ — values.yaml (prod, gyopart.local) + values-dev.yaml (dev, gyopart-dev.local, namespace gyopart-dev). ArgoCD apps in cluster_config/argocd/gyopart.yaml and gyopart-dev.yaml — applied manually with kubectl apply (not auto-discovered). gyopart-dev tracks dev branch via targetRevision: dev. Secrets (junkyard-credentials, parts-interchange-credentials) applied manually with kubectl — never committed. Ingresses: gyopart.local→ui:80, api.gyopart.local→gyopart-api:8200, admin.gyopart.local→admin-api:8300.
