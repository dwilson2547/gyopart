---
title: NHTSA Batch VIN Decode — Endpoint Behavior & Gotchas
date: 2026-05-31
tags: nhtsa, vin, pipeline, mapping-pipeline
---

POST to https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/. Body fields: DATA (semicolons-separated VINs) and format (json/csv/xml). CRITICAL: format must be in the POST body — passing as query param silently returns XML instead of JSON. Hard limit of 50 VINs; 51+ returns HTTP 200 with Execution Error and no decoded data. Invalid/short VINs do not abort the batch — each gets its own error result row. Batch returns full Make/Model/Year even for ErrorCode=1 (check digit mismatch) where the single-VIN endpoint returns nulls for those fields. Use the same error filter: skip if "11" in error_code. ~16x faster than individual calls with 1s sleep. Full findings doc: junkyard-platform/docs/nhtsa-batch-endpoint.md. POC script: junkyard-platform/pipeline/nhtsa_batch_poc.py.
