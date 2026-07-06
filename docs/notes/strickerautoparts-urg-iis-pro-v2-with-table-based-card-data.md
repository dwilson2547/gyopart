---
title: strickerautoparts — URG IIS Pro v2 with table-based card data
date: 2026-05-31
tags: urg, iis-pro-v2, strickerautoparts
---

scraper.py at junkyard-inventory-scrapers/strickerautoparts/scraper.py. SOURCE=stricker_auto_parts. Single location (Batavia OH). Unlike speedwayap/arizonaautoparts which use <b>Label:</b> text nodes, this site stores card fields in 2-column <tr><td>Key:</td><td>Value</td></tr> table rows — parsed with _table_data(). Card selector is .iis-col-sm-4 .card.card-price (nested: outer iis-col-sm-4 div contains inner card-price div; id is on the inner div). Make/Model only appear in table on latest-arrivals, not on make/model pages — pass URL slugs as make_hint/model_hint and call _slug_to_label() to replace underscores with spaces. Image is lazy-loaded via data-src (not src). Enter Date used on latest-arrivals.
