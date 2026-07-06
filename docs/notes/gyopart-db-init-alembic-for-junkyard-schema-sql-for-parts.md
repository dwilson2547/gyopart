---
title: Gyopart DB init: Alembic for junkyard, schema.sql for parts
date: 2026-05-31
tags: k8s, postgres, schema, fastapi
---

Both DBs use Base.metadata.create_all() in FastAPI lifespan hooks — idempotent, no separate init Job needed. junkyard_common.models.Base covers junkyard_inventory (inventory_api + admin_api). parts_interchange_common.models.Base covers parts_interchange (gyopart-api). Schema authority: dwilson-junkyard-common and dwilson-parts-interchange-common on PyPI are the single source of truth for both schemas.
