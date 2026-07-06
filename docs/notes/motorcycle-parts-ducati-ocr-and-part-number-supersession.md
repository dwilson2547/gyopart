---
title: Motorcycle parts — Ducati OCR and part number supersession
date: 2026-05-31
tags: motorcycles, ducati, ocr, supersession, schema
---

Ducati data comes from Issuu PDF catalogs, not a live web catalog. pdf_parser.py uses pdfplumber + multi-language regex heuristics — success rates are poor because catalogs are scanned raster pages, not clean vector PDFs. Fix: send each PDF page as an image to a vision LLM (Claude) to extract the parts table structurally; maps directly into the Diagram/Part schema. Part number supersession (Ducati changes numbers frequently — same part can have 3 different numbers over 20 years): model as part_supersessions(old_part_number, new_part_number, source, effective_date, notes). Walk the chain with a recursive CTE; current part number = new_part_number that never appears as old_part_number. Add this table from day one. Workshop manuals (ducati_owners_manuals scraper exists): store as separate 'manuals' table (brand, model, year, title, local_path) in same moto schema.
