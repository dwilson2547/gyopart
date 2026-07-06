---
title: budgetupullit — per-make enumeration, all-known incremental skip
date: 2026-05-31
tags: budgetupullit, ssr, incremental
---

scraper.py at junkyard-inventory-scrapers/budgetupullit/scraper.py. SOURCE=budget_upullit. No single inventory endpoint — must enumerate 39 makes via GET /current-inventory/?make={MAKE}&model=. Pick last .resultsTable (two on page: header + results). Columns: Year, Make, Model, Stock#(3), Row(4), VIN(5), Date(6). Stock# in extras[stock_number]. Incremental: fetch /new-arrivals/ → if ALL VINs subset of known_vins, skip full crawl entirely (saves 39 requests). If any new VINs, run full crawl with deactivation. Date formats differ: inventory=MM.DD.YY (dots), new-arrivals=MM/DD/YY (slashes) — _parse_arrival_date tries both.
