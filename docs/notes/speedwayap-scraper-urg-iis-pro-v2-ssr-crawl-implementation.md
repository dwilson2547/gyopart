---
title: speedwayap scraper — URG IIS Pro v2 SSR crawl implementation
date: 2026-05-31
tags: urg, iis-pro-v2, speedwayap, ssr
---

scraper.py at junkyard-inventory-scrapers/speedwayap/scraper.py. SOURCE=speedway_ap, single location (Joliet IL). Strategy: GET /parts/makes/ → /parts/{MAKE}/ → /parts/{MAKE}/{MODEL}/ → parse .iis-col-sm-4 card divs. _labeled_text() finds <b>Label:</b> then reads NavigableString next_sibling. VIN in <b>Vin :</b> (note space before colon). CDN yardpath is mi34 (not the urgid IL22). Incremental: try /latest-arrivals/ first, stop on first known VIN; fall back to full crawl if none match. Removed-vehicle deactivation only runs in full_crawl_mode.
