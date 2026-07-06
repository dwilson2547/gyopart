---
title: u-pull-n-save: vehicleID-based deactivation for APIs without VIN in search
date: 2026-05-31
tags: postgresql, jsonb, u-pull-n-save, deactivation
---

When a search endpoint returns vehicleIDs but no VINs, store vehicleID in extras["vehicle_id"] and use JSONB queries for deactivation: `Vehicle.extras["vehicle_id"].astext.in_([str(v) for v in ids])`. Only fetch the detail endpoint (which has VIN) for new vehicleIDs not already in DB — keeps detail calls to a minimum. Still-present existing vehicles get last_seen_at updated via bulk JSONB filter. The year/make/model matrix can be ~2000-4000 combos; WebCacheClient with 23hr TTL makes subsequent same-day runs cheap.
