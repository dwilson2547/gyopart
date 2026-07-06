---
title: parts_interchange_common — Shared Schema Library
date: 2026-05-31
tags: parts-interchange, schema, pypi
---

Published to PyPI as dwilson-parts-interchange-common. Lives at gyopart/parts-interchange/parts_interchange_common/ with db.py (get_engine reads PARTS_INTERCHANGE_DATABASE_URL), models.py (18 tables: manufacturer, year, make, model, trim, engine, category, subcategory, image, part, car, diagram, feedback, scrape_run + association tables car_parts, car_diagrams, diagram_parts, part_images). gyopart-api imports via thin re-export in src/models.py and calls Base.metadata.create_all() in FastAPI lifespan. car_categories removed — no CSVs exist and categories are derivable from car_diagrams + diagram.category_id. image table has imgcache_hash/imgcache_bucket columns not present in bulk-load CSVs.
