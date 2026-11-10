---
title: tearapart: WP nonce must not be cached — expires in ~12 hours
date: 2026-05-31
tags: wordpress, nonce, tearapart
---

The sif_ajax_nonce on tearapart.com is valid ~12 hours. Fetch /inventory/ fresh each run (no WebCache call for the nonce page). Cache the actual POST responses (action=sif_search_products) with a custom cache key like AJAX_URL+?action=...&store=... One POST per store returns full inventory in a single response — no pagination. VIN present in every record via the `vin` field.

**Update 2026-11-10:** "fresh" isn't enough — /inventory/ itself is served from Cloudflare + a server page cache (both report HIT), which can hand out an expired nonce. Fetch it with a unique query string (`?_=<ns>`, misses both caches). A rejected nonce comes back as HTTP 200 with the plain-text body `test failed!` (not JSON), which surfaced as `JSONDecodeError ... char 0`; the scraper now refetches and retries the store once.
