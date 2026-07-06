---
title: chesterfieldauto: ASP.NET anti-forgery token is session-scoped, never cache token page
date: 2026-05-31
tags: aspnet, chesterfieldauto, token
---

chesterfieldauto.com uses __RequestVerificationToken (ASP.NET Core anti-forgery). Token is session-scoped — one GET /search-our-inventory-by-location is enough per run; DO NOT cache this response (token tied to session cookie). POST per make-id to ?SelectedMake.Id={id}. VIN extracted from button data-target attribute: last 17 chars matching [A-HJ-NPR-Z0-9]{17}. Modal divs (id=MAKE+VIN) are pre-rendered in same HTML as search results — no extra requests for stock#/transmission/drive extras.
