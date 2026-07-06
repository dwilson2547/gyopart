---
title: Gyopart-ui nginx proxy pattern
date: 2026-05-31
tags: gyopart-ui, nginx, docker, vite
---

gyopart-ui container uses nginx to proxy /v1/ → gyopart-api:8200, so no API URL is baked into the image. api.ts sets baseURL to import.meta.env.VITE_API_BASE_URL ?? '' (empty string = relative). One image works in all environments. For local dev, vite.config.ts has server.proxy: {'/v1': 'http://localhost:8200'}. nginx config at gyopart/gyopart-ui/nginx.conf.
