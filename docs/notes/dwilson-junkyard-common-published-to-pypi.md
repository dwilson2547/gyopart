---
title: dwilson-junkyard-common — Published to PyPI
date: 2026-05-31
tags: parts-interchange, junkyard-common, pypi, package
---

Package name: dwilson-junkyard-common. Import as: junkyard_common. Published by Daniel Wilson. Install: pip install dwilson-junkyard-common. Contains: models.py (SQLAlchemy ORM — Location, Vehicle, MappingRule, MappingDiscrepancy, ScrapeRun, VinCache), db.py (get_engine, get_session — reads JUNKYARD_DATABASE_URL env var). Source lives in gyopart/junkyard-platform/junkyard_common/ with pyproject.toml at the junkyard-platform/ root. Vehicle has 36 columns — flat schema, no VehicleDetail, extras JSONB for yard-specific overflow. Verified working via clean venv install from PyPI.
