---
title: gyopart — Canonical Schema & Key Paths
date: 2026-05-31
tags: parts-interchange, schema, file-paths
---

Schemas: junkyard_inventory (scraper data) and parts_interchange (parts catalog) on separate k8s postgres instances (prod: postgres.postgres.svc.cluster.local, dev: postgres-dev.postgres.svc.cluster.local). junkyard_inventory tables: Location, Vehicle (flat), MappingRule, MappingDiscrepancy, ScrapeRun, VinCache — defined in junkyard_common (dwilson-junkyard-common on PyPI) at gyopart/junkyard-platform/junkyard_common/models.py. parts_interchange tables (18): manufacturer, year, make, model, trim, engine, category, subcategory, image, part, car, diagram, feedback, scrape_run + car_parts, car_diagrams, diagram_parts, part_images — defined in parts_interchange_common (dwilson-parts-interchange-common on PyPI) at gyopart/parts-interchange/parts_interchange_common/models.py. gyopart-api re-exports from parts_interchange_common via src/models.py and calls create_all() on startup. Alembic root = gyopart/junkyard-inventory-scrapers/. Key paths: inventory_api = gyopart/junkyard-platform/inventory_api/. admin_api = gyopart/junkyard-platform/admin_api/. gyopart-api = gyopart/gyopart-api/ (port 8200). gyopart-ui = gyopart/gyopart-ui/ (port 5173).
