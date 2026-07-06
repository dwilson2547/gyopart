---
title: Gyopart geocoding: uszipcode for pipeline, OSM deferred
date: 2026-05-31
tags: pipeline, geocoding
---

Pipeline geocodes Location rows (sets lat/lng) using uszipcode — already a dep of inventory_api, no new infrastructure. Zip centroid accuracy sufficient for Haversine radius junkyard search. inventory_api uses uszipcode for the user zip → lat/lng lookup at query time. Nominatim/OSM is future work if address-level precision is needed. Pipeline should geocode locations with null lat/lng on each run.
