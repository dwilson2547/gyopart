---
title: Gyopart two-database architecture: junkyard_inventory + parts_interchange
date: 2026-05-31
tags: architecture
---

gyopart uses two Postgres databases: junkyard_inventory (scraped live inventory, schema authority: dwilson-junkyard-common package) and parts_interchange (OEM parts catalog, schema authority: dwilson-parts-interchange-common package). gyopart-api reads parts_interchange. inventory_api reads junkyard_inventory. Resolution pipeline links the two via Vehicle.car_id → Car.id. Prod: postgres.postgres.svc.cluster.local. Dev: postgres-dev.postgres.svc.cluster.local.
