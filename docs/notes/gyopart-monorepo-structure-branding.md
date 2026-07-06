---
title: gyopart — Monorepo Structure & Branding
date: 2026-05-31
tags: structure, monorepo
---

Project rebranded to gyopart (gyopart.com — Get Your Own Part). Replaced parts-interchange.com. All repos consolidated into a flat monorepo at automotive/gyopart/ (no git submodules). Structure: gyopart-api/ (FastAPI port 8200), gyopart-ui/ (React/Vite port 5173), junkyard-platform/ (inventory_api + admin_api + junkyard_common), junkyard-inventory-scrapers/, parts-interchange/ (legacy parts catalog data, loader, docs). scrape_stack stays as a separate universal repo — not part of gyopart, just referenced. parts-interchange is the underlying data source for the parts catalog; gyopart-api/gyopart-ui are the product layer on top.
