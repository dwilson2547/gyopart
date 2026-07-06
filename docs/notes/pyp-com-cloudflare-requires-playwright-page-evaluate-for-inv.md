---
title: pyp.com: Cloudflare requires Playwright; page.evaluate() for inventory API calls
date: 2026-05-31
tags: playwright, cloudflare, pyp, lkq
---

All requests to pyp.com are Cloudflare-protected. Must use Playwright (chromium, headless). Navigate to seed URL to clear CF challenge, then use page.evaluate() with fetch() + {"x-requested-with": "XMLHttpRequest"} header for inventory API calls. Location list (62 locations) is in _locationList JS var on any inventory page. Inventory endpoint: /DesktopModules/pyp_vehicleInventory/getVehicleInventory.aspx?page={N}&filter=&store={code}. Paginated 25/page, newest first; stop on pypvi_end class. Per-location deactivation: only deactivate if location was fully scraped (not stopped early on known VIN).
