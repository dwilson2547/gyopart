# Wrench A Part — Custom REST API Pattern

**Site:** wrenchapart.com  
**API:** https://api.wrenchapart.com

## Key Learnings

- Entirely custom REST API, not a known SaaS platform
- No auth, no pagination — single `GET /v1/vehicles` returns the full ~11K inventory as a flat JSON array
- VINs always present in every record
- `days=N` query param is the only supported time filter; `after=date` is ignored
- `locationId` and `yardId` appear equivalent as filter params
- `GET /locations` (no `/v1/` prefix) returns full address + phone + social for all yards
- The `/v1/yards` and `/v1/locations` endpoints exist but return only the string `"success"` — useless
- Recent arrivals pages on the frontend call `?locationId={id}&days=10`; useful as a template for incremental runs
- GPS row coordinates included per vehicle (lat/lon of the physical yard row), though some yards have nulls
