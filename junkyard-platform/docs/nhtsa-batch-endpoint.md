# NHTSA DecodeVINValuesBatch — POC Findings

Tested live against `https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/`  
POC script: `pipeline/nhtsa_batch_poc.py`  
Date: 2026-05-20

---

## Endpoint Basics

- **Method:** `POST`
- **Content-Type:** `application/x-www-form-urlencoded`
- **Body fields:**
  - `DATA` — semicolon-separated VINs (e.g. `VIN1;VIN2;VIN3`)
  - `format` — `json` | `csv` | `xml` (see Format section below)

---

## Format Behavior

| How format is specified | Result |
| --- | --- |
| `format=json` in POST **body** | Returns JSON (`Content-Type: application/json`) ✅ |
| `format=json` as **query param** | Silently ignored — returns XML (`Content-Type: application/xml`) ⚠️ |
| `format=csv` in POST **body** | Returns CSV (`Content-Type: application/octet-stream`) |
| `format=xml` in POST **body** | Returns XML (`Content-Type: application/xml`) |

**Key finding:** `format` must be a POST body field, not a query parameter. Passing it as a query param causes the API to silently fall back to XML with no error — this is a silent failure mode to guard against.

For our pipeline, `format=json` in the body is the right choice. The JSON response shape is a flat dict per VIN (all decoded fields as top-level keys), which is easier to parse than the single-VIN endpoint's `[{Variable, Value}]` list format.

---

## Batch Size Limit

- **Maximum:** 50 VINs per request
- **At 50:** Returns 50 results normally (elapsed ~1.65s in testing)
- **At 51+:** Returns HTTP 200 but body contains a single result with `"Message": "Execution Error"` — no VINs decoded

Implementation must enforce the 50-VIN hard limit by chunking before sending.

---

## Response Shape (JSON)

The batch endpoint returns a **flat dict per VIN**, not the Variable/Value list format of the single-VIN endpoint:

```json
{
  "Count": 5,
  "Message": "Results returned successfully...",
  "SearchCriteria": null,
  "Results": [
    {
      "VIN": "1HGCM82633A004352",
      "Make": "HONDA",
      "Model": "Accord",
      "ModelYear": "2003",
      "ErrorCode": "0",
      "ErrorText": "0 - VIN decoded clean...",
      "BodyClass": "Sedan/Saloon",
      "DriveType": "FWD/Front-Wheel Drive",
      ...150+ more fields
    }
  ]
}
```

Each result object contains 150+ fields. Fields with no data are empty strings (not null).

---

## Error Handling in Batches

Invalid or problematic VINs do **not** abort the batch — each VIN gets its own result row with an error code.

| Scenario | HTTP Status | ErrorCode | Make/Model/Year |
| --- | --- | --- | --- |
| Clean VIN | 200 | `0` | Populated |
| Check digit mismatch (ErrorCode 1) | 200 | `1` | **Populated** (see note below) |
| Invalid VIN (`000...`) | 200 | `1,7,11,400` | Empty |
| Short VIN (< 17 chars) | 200 | `6` | Empty |

**Important — ErrorCode 1 behavior differs from single-VIN endpoint:**  
The batch endpoint returns full decoded data (Make, Model, ModelYear, etc.) even when ErrorCode=1 (check digit mismatch). The single-VIN endpoint appears to return null/empty for many of these fields on the same VINs. This means the batch warm-up will successfully cache some VINs that the per-VIN fallback path currently treats as errors. The existing error filter (`"11" in error_code`) is safe to reuse — ErrorCode `1` alone does not contain `"11"` so those VINs will be stored with their decoded data.

---

## Timing

Measured against 5 VINs (each already-decoded by NHTSA, not cold):

| Approach | Elapsed |
| --- | --- |
| 5 individual GET calls with `time.sleep(1)` between each | 6.51s |
| 1 batch POST (5 VINs) | 0.41s |
| **Speedup** | **~16x** |

For a run of 1,000 uncached VINs:

- Individual path: ~17 minutes (1s sleep × 1,000 + network)
- Batch path: ~8 requests × ~1.5s each ≈ **~12 seconds**

---

## Implementation Notes

1. **Chunk input into batches of ≤50** before sending — 51+ triggers "Execution Error" silently.
2. **Always pass `format=json` in the POST body**, not as a query param.
3. **Filter out already-cached VINs before batching** — no point hitting the API for data we already have.
4. **Filter out non-17-char VINs before batching** — they produce ErrorCode 6 and waste a slot; keep the existing pre-check in `decode_vin`.
5. **Use the same error filter as the single path** (`"11" in error_code`) to detect genuine no-decode results. ErrorCode 1 (check digit only) still yields usable data — do not skip those results.
6. **Rate limiting:** NHTSA doesn't publish rate limits for this endpoint, but a short sleep (~0.5s) between batch requests is prudent for large runs.
7. **The `VIN` key is present in every result row** — use it to map results back to the input list since response order may not match input order.

---

## Fields We Use

From the batch response, the pipeline needs:

| Batch key | Pipeline use |
| --- | --- |
| `VIN` | Map result back to input VIN |
| `Make` | Store in VinCache / car resolution |
| `Model` | Store in VinCache / car resolution |
| `ModelYear` | Store in VinCache / car resolution |
| `Trim` | Store in VinCache |
| `ErrorCode` | Determine cache success vs error |

All other fields can be ignored for the current pipeline.
