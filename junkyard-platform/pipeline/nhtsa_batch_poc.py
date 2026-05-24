"""
POC: NHTSA DecodeVINValuesBatch endpoint exploration.

Tests format options (json/csv/xml), whether format is a query param or body field,
batch size behavior, and error handling for invalid/pre-1981 VINs.

Run: python -m pipeline.nhtsa_batch_poc
"""
import time

import requests

BATCH_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"
SINGLE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"

# Mix of valid, invalid, and pre-1981 VINs for thorough coverage.
VALID_VINS = [
    "1FTFW1ET5DFC10312",  # 2013 Ford F-150
    "1HGCM82633A004352",  # 2003 Honda Accord
    "2T1BURHE0JC043821",  # 2018 Toyota Corolla
    "1G1ZT53806F109149",  # 2006 Chevrolet Cobalt
    "1N4AL3AP7JC231503",  # 2018 Nissan Altima
]
INVALID_VIN = "00000000000000000"   # 17 chars but not a real VIN
SHORT_VIN   = "1FTFW1ET5DFC103"    # too short (15 chars)
PRE_81_VIN  = "1HGCM82633A00"      # pre-standardization era placeholder


def separator(label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


# ---------------------------------------------------------------------------
# 1. Format as body field (expected to work per NHTSA docs)
# ---------------------------------------------------------------------------
separator("TEST 1 — format=json as body field (POST form data)")
payload = {"DATA": ";".join(VALID_VINS), "format": "json"}
resp = requests.post(BATCH_URL, data=payload, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('Content-Type')}")
try:
    j = resp.json()
    results = j.get("Results", [])
    print(f"Results count: {len(results)}")
    print(f"Keys in first result: {list(results[0].keys()) if results else 'N/A'}")
    # Show Make/Model/Year/ErrorCode for each VIN result
    vin_fields = ["VIN", "Make", "Model", "ModelYear", "ErrorCode", "ErrorText"]
    for r in results:
        vals = {f: r.get(f, "") for f in vin_fields}
        print(f"  {vals}")
except Exception as e:
    print(f"JSON parse error: {e}")
    print(resp.text[:500])

time.sleep(1)

# ---------------------------------------------------------------------------
# 2. Format as query parameter
# ---------------------------------------------------------------------------
separator("TEST 2 — format=json as query param")
payload2 = {"DATA": ";".join(VALID_VINS[:3])}
resp2 = requests.post(BATCH_URL + "?format=json", data=payload2, timeout=30)
print(f"Status: {resp2.status_code}")
print(f"Content-Type: {resp2.headers.get('Content-Type')}")
try:
    j2 = resp2.json()
    print(f"Results count: {len(j2.get('Results', []))}")
except Exception as e:
    print(f"JSON parse error: {e}")
    print(resp2.text[:200])

time.sleep(1)

# ---------------------------------------------------------------------------
# 3. CSV format
# ---------------------------------------------------------------------------
separator("TEST 3 — format=csv as body field")
payload3 = {"DATA": ";".join(VALID_VINS[:3]), "format": "csv"}
resp3 = requests.post(BATCH_URL, data=payload3, timeout=30)
print(f"Status: {resp3.status_code}")
print(f"Content-Type: {resp3.headers.get('Content-Type')}")
print(f"First 500 chars of response:\n{resp3.text[:500]}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 4. XML format
# ---------------------------------------------------------------------------
separator("TEST 4 — format=xml as body field")
payload4 = {"DATA": ";".join(VALID_VINS[:3]), "format": "xml"}
resp4 = requests.post(BATCH_URL, data=payload4, timeout=30)
print(f"Status: {resp4.status_code}")
print(f"Content-Type: {resp4.headers.get('Content-Type')}")
print(f"First 500 chars of response:\n{resp4.text[:500]}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 5. Invalid VIN mixed into a batch
# ---------------------------------------------------------------------------
separator("TEST 5 — invalid VIN mixed into batch")
mixed = VALID_VINS[:2] + [INVALID_VIN]
payload5 = {"DATA": ";".join(mixed), "format": "json"}
resp5 = requests.post(BATCH_URL, data=payload5, timeout=30)
print(f"Status: {resp5.status_code}")
try:
    j5 = resp5.json()
    results5 = j5.get("Results", [])
    print(f"Results count: {len(results5)}")
    for r in results5:
        print(f"  VIN={r.get('VIN')}  Make={r.get('Make')!r}  ErrorCode={r.get('ErrorCode')!r}")
except Exception as e:
    print(f"JSON parse error: {e}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 6. Short VIN in batch
# ---------------------------------------------------------------------------
separator("TEST 6 — short (non-17-char) VIN in batch")
payload6 = {"DATA": SHORT_VIN, "format": "json"}
resp6 = requests.post(BATCH_URL, data=payload6, timeout=30)
print(f"Status: {resp6.status_code}")
try:
    j6 = resp6.json()
    results6 = j6.get("Results", [])
    print(f"Results count: {len(results6)}")
    for r in results6:
        print(f"  VIN={r.get('VIN')}  ErrorCode={r.get('ErrorCode')!r}")
except Exception as e:
    print(f"Response text: {resp6.text[:300]}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 7. Batch of exactly 50 VINs (max limit check)
# ---------------------------------------------------------------------------
separator("TEST 7 — batch of 50 VINs (max limit)")
fifty_vins = (VALID_VINS * 10)[:50]
payload7 = {"DATA": ";".join(fifty_vins), "format": "json"}
t0 = time.time()
resp7 = requests.post(BATCH_URL, data=payload7, timeout=60)
elapsed = time.time() - t0
print(f"Status: {resp7.status_code}  elapsed: {elapsed:.2f}s")
try:
    j7 = resp7.json()
    print(f"Results count: {len(j7.get('Results', []))}")
except Exception as e:
    print(f"JSON parse error: {e}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 8. Batch of 51 VINs (over limit check)
# ---------------------------------------------------------------------------
separator("TEST 8 — batch of 51 VINs (over limit)")
fiftyone_vins = (VALID_VINS * 11)[:51]
payload8 = {"DATA": ";".join(fiftyone_vins), "format": "json"}
resp8 = requests.post(BATCH_URL, data=payload8, timeout=60)
print(f"Status: {resp8.status_code}")
try:
    j8 = resp8.json()
    results8 = j8.get("Results", [])
    print(f"Results count: {len(results8)}")
    # Check for error message in response
    msg = j8.get("Message", "")
    if msg:
        print(f"Message: {msg}")
except Exception as e:
    print(f"Response text: {resp8.text[:300]}")

time.sleep(1)

# ---------------------------------------------------------------------------
# 9. Timing — 5 single calls vs 1 batch call
# ---------------------------------------------------------------------------
separator("TEST 9 — timing: 5 individual calls vs 1 batch call (5 VINs)")

t0 = time.time()
for vin in VALID_VINS:
    r = requests.get(SINGLE_URL.format(vin=vin), timeout=15)
    r.raise_for_status()
    time.sleep(1)
single_elapsed = time.time() - t0
print(f"5 individual calls (with 1s sleep each): {single_elapsed:.2f}s")

t0 = time.time()
rb = requests.post(BATCH_URL, data={"DATA": ";".join(VALID_VINS), "format": "json"}, timeout=30)
batch_elapsed = time.time() - t0
print(f"1 batch call (5 VINs):                  {batch_elapsed:.2f}s")
print(f"Speedup factor:                         {single_elapsed / batch_elapsed:.1f}x")

# ---------------------------------------------------------------------------
# 10. Verify field parity — batch vs single for same VIN
# ---------------------------------------------------------------------------
separator("TEST 10 — field parity: batch result vs single result for same VIN")
test_vin = VALID_VINS[0]

single_resp = requests.get(SINGLE_URL.format(vin=test_vin), timeout=15)
single_data = {r["Variable"]: r["Value"] for r in single_resp.json()["Results"]}

time.sleep(1)

batch_resp = requests.post(BATCH_URL, data={"DATA": test_vin, "format": "json"}, timeout=30)
batch_results = batch_resp.json()["Results"]
batch_data = batch_results[0] if batch_results else {}

fields_of_interest = ["Make", "Model", "ModelYear", "Trim", "ErrorCode", "ErrorText",
                       "BodyClass", "DriveType", "EngineModel", "FuelTypePrimary"]
print(f"{'Field':<25} {'Single':>30} {'Batch':>30}")
print("-" * 87)
for field in fields_of_interest:
    sv = (single_data.get(field) or "").strip()
    bv = (batch_data.get(field) or "").strip()
    mismatch = " <-- DIFFERS" if sv != bv else ""
    print(f"{field:<25} {sv:>30} {bv:>30}{mismatch}")

print("\nDone.")
