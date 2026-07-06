---
title: ipullupull — CSV feeds, header whitespace, Fresh Set column
date: 2026-05-31
tags: ipullupull, csv, multi-location
---

scraper.py at junkyard-inventory-scrapers/ipullupull/scraper.py. SOURCE=ipullupull. 4 CSV feeds at ipullupull.com/{yard}.csv (fresno/pomona/sacramento/stockton). All column headers after Date Added have a leading space — must strip keys: {k.strip(): v for k, v in row.items()}. Fresh Set==Yes marks newest batch; stored in extras[fresh_set]=True. Date Added is YYYY-MM-DD. No incremental logic — 4 requests total is cheap enough to always full-sync with deactivation.
