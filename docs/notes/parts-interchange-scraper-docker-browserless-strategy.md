---
title: Parts Interchange — Scraper Docker & Browserless Strategy
date: 2026-05-31
tags: parts-interchange, docker, scrapers, browserless, infrastructure
---

Single omnibus Docker image for all scrapers (junkyard-scrapers:x.y.z). No per-scraper images. CronJob manifest specifies which scraper to run via command/args. Playwright scrapers connect to shared browserless instance in scrape_stack via CDP — no browser binaries in image. pip install playwright only (no playwright install), saving ~800MB-1.2GB vs embedded browsers. Browserless URL passed as env var BROWSERLESS_URL=ws://browserless:3000 in CronJob manifest. TODO when wiring scrapers: check/tune browserless max concurrent sessions config in scrape_stack to avoid overwhelming it with simultaneous CronJob runs. Dockerfile uses single build arg approach, requirements.txt includes dwilson-junkyard-common pinned version.
