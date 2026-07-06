---
title: parts-loader-v2 — Bulk Load Gotchas
date: 2026-05-31
tags: parts-interchange, parts-loader, postgres, gotcha
---

SET session_replication_role = replica requires superuser — gyopart_dev is not a superuser, so this call must be removed. Load order in LOAD_ORDER already respects FK dependencies so the flag is not needed. image table COPY requires explicit column list (id, name, bucket_path, url, alt_text, saved, uploaded, manufacturer_id) because CSVs omit imgcache_hash and imgcache_bucket; use COPY_COLUMNS dict for per-table overrides. --init-schema now calls Base.metadata.create_all() from parts_interchange_common instead of running schema.sql (deleted). schema.sql is gone — parts_interchange_common is the single source of truth.
