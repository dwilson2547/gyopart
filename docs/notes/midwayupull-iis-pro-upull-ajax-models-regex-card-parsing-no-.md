---
title: midwayupull — iis-pro-upull: AJAX models, regex card parsing, no /latest-arrivals/
date: 2026-05-31
tags: urg, iis-pro-upull, midwayupull, multi-location, ajax
---

scraper.py at junkyard-inventory-scrapers/midwayupull/scraper.py. SOURCE=midway_upull. Platform is iis-pro-upull (U-Pull variant) not iis-pro-v2. Makes parsed from <option> tags on /search-inventory/ (falls back to hardcoded list of 59). Models via POST admin-ajax.php action=getAllModelsIISupull&make={MAKE} — response has model/value pairs; value is URL slug. URL slug encoding: spaces→_, hyphens→~, slashes→. Inventory pages at /inventory/{MAKE_SLUG}/{MODEL_SLUG}/. Cards are .car-details-uPull divs; fields parsed with regex on card.get_text(newline) — not <b>Label:</b> nodes or table rows. Location from text field Location: Liberty U-Pull / Muncie U-Pull → MO09/MO38. CDN yardpath mo06, image suffix _0.jpg (not _1.jpg). No /latest-arrivals/ page — always full crawl. Always deactivates removed vehicles.
