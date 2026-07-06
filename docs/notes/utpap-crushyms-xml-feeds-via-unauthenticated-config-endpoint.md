---
title: utpap — CrushYMS XML feeds via unauthenticated config endpoint
date: 2026-05-31
tags: utpap, crushyms, xml, multi-location
---

scraper.py at junkyard-inventory-scrapers/utpap/scraper.py. SOURCE=utpap. Feed URLs from unauthenticated GET .../api/admin/yard-config/utah_pic_a_part: Orem=http://45.79.157.162/1065_inventory.xml (client 1065), Ogden=http://45.79.157.162/1064_inventory.xml (client 1064). Plain HTTP intentional — server has no HTTPS. XML: <INVENTORY> root, <ASSET> children. Filter iSTATUS==0 for active vehicles only. MILEAGE field often shows 1 as placeholder — stored as-is. YARD_IN_DATE is ISO 8601 with ms (datetime.fromisoformat handles it). Photo URLs: utpap.com/{Orem|Ogden}-inventory-photos/{STOCKNUMBER}.jpeg.
