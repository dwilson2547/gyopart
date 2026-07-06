---
title: Gyopart scraper pattern: junkyard_common + WebCacheClient + RequestAuthClient
date: 2026-05-31
tags: patterns
---

All scrapers use junkyard_common.db.get_engine() via JUNKYARD_DATABASE_URL env var. Write Location, Vehicle, ScrapeRun rows. Use WebCacheClient for HTML caching and RequestAuthClient for rate limiting (both from scrape_stack). Dedup key is VIN as source_key for all VIN-present scrapers. source_key falls back to stock_number for pre-VIN era vehicles.
