---
title: picknpullsa — pre-1981 short VIN handling
date: 2026-05-31
tags: picknpullsa, ssr, vin
---

scraper.py at junkyard-inventory-scrapers/picknpullsa/scraper.py. SOURCE=picknpullsa. Table id=vehicles-inventory; column order: Year, Make, Model, Color, VIN(4), Engine(5), Row(6), Arrival Date(7) — differs from cfpap (VIN is at index 4, not 7). Pre-1981 vehicles carry short manufacturer serials not 17-char VINs; stored as source_key with vin=None in the Vehicle row (keeps dedup stable, mapping pipeline skips them). Engine stored in extras[engine]. Single GET, always full crawl.
