---
title: Motorcycle parts system — scope and architecture
date: 2026-05-31
tags: motorcycles, architecture, scope
---

Standalone reference system (not gyopart) for motorcycle OEM parts. Lives at automotive/motorcycles/ with brand subdirs: aprilia, bmw, ducati, ducati_owners_manuals, harley, honda, kawasaki, suzuki, yamaha. Aprilia and Kawasaki already share the correct unified schema: Motorcycle → Diagram → DiagramPart → Part with M2M associations and content-addressed image dedup — use this as the canonical pattern for all brands. Target: own 'moto' schema in shared Postgres (not a separate instance). Separate from gyopart entirely — no junkyard inventory, no VIN pipeline, no location search. Reference tool scope: pick a bike, browse diagrams, find OEM part numbers, see supersession chain.
