---
title: las-parts scraper — location via CDN image URL prefix
date: 2026-05-31
tags: urg, iis-pro-v2, las-parts, multi-location
---

scraper.py at junkyard-inventory-scrapers/las-parts/scraper.py. SOURCE=las_parts. 3 yard IDs (NJ12, NJ29, II08) inferred from CDN image URL via regex cloudfront\.net/([^/]+)/images/ (lowercase prefix e.g. nj12 → NJ12). Vehicles with missing or non-cloudfront image fall back to UNKNOWN location row. 4 Location rows total. latest-arrivals uses Enter Date (not Arrive Date or Purchase Date). preview_image_url only set if src contains cloudfront (skips plugin placeholder). AJAX location endpoints return 400 on this site — CDN URL is the only location signal.
