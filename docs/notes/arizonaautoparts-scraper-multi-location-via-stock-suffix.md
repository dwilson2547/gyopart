---
title: arizonaautoparts scraper — multi-location via stock suffix
date: 2026-05-31
tags: urg, iis-pro-v2, arizonaautoparts, multi-location
---

scraper.py at junkyard-inventory-scrapers/arizonaautoparts/scraper.py. SOURCE=arizona_auto_parts. Single urgid AZ03 but 2 physical yards; location inferred from trailing alpha char of stock number (A=Phoenix, B=Tucson, U=unknown). Seeds 3 Location rows up front keyed by suffix. Card selector is .card-price (not .iis-col-sm-4 as on speedwayap). latest-arrivals uses Arrive Date not Purchase Date. Image URL extracted from img src directly (CDN suffix is per-image numeric, not predictable). ScrapeRun.location_id=None for multi-location scrapers. location_id re-applied on conflict update in case a vehicle moves yards.
