---
title: Admin API — no auth by design
date: 2026-05-31
tags: admin-api, security, traefik
---

admin_api has no authentication middleware. All routes (/admin/*) are unprotected at the app level — the network boundary (private LAN, Traefik ingress, not exposed externally) is the only protection needed. Previously had X-Admin-Key header middleware + ADMIN_API_KEY secret, removed as security theater. If auth is ever needed, add it at the Traefik ingress level (BasicAuth middleware) rather than in the app.
