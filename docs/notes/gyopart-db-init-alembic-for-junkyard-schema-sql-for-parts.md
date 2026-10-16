---
title: Gyopart DB init: Alembic for junkyard, schema.sql for parts
date: 2026-05-31
tags: k8s, postgres, schema, fastapi
---

inventory_api and gyopart-api call Base.metadata.create_all() in their FastAPI lifespan hooks (idempotent, creates missing tables only, never alters). admin_api no longer does (removed 2026-10-15, admin rewrite phase 5): it starts with its database down. Column changes to junkyard_inventory go through Alembic in junkyard-platform/db/, applied by hand (gyopart CLAUDE.md). junkyard_common.models.Base covers junkyard_inventory. parts_interchange_common.models.Base covers parts_interchange (gyopart-api). Schema authority: dwilson-junkyard-common and dwilson-parts-interchange-common on PyPI are the single source of truth for both schemas.
