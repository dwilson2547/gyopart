---
title: parts-direct Lexus scraper — save location and run pattern
date: 2026-05-31
tags: parts-direct, lexus, scraper, parts-interchange
---

Scraper is parts-interchange/parts-direct/update-scraper/run.py. Run with: cd parts-interchange/parts-direct/update-scraper && WEBCACHE_URL=http://webcache.scrapestack-dev.local IMGCACHE_URL=http://imgcache.scrapestack-dev.local REQUEST_AUTH_URL=192.168.0.63:9000 python3 run.py lexus 3 30. Save data lands in ~/rsync-dump/lexus/ (not the repo or /tmp) — tree.json, parts.json, imgs.json, blank_tree.json. Low-priority saves throttle to every 30 min; parts.json reached ~151MB and tree.json ~14MB after a full overnight run. Stops on 403s from image pulls if the Playwright window is closed externally — restart cleanly by sending SIGINT (triggers a save) then SIGTERM.
