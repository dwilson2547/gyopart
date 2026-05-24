# ASP.NET MVC Junkyard Sites (Classic & Core)

## Variants

| Variant | Applies to | CSRF token? |
|---------|-----------|-------------|
| **ASP.NET Core MVC** | chesterfieldauto.com | Yes — `__RequestVerificationToken` (`CfDJ8...`) |
| **ASP.NET MVC Classic** | sturtevantauto.com | No |

### Identifying Classic vs Core
- Core: token field `input[name="__RequestVerificationToken"]` present; scripts in `/lib/`
- Classic: no token; scripts in `/Scripts/`; bundle paths (`/bundles/...`) may 404 while individual script paths still work

---

## ASP.NET Core MVC

**Applies to:** chesterfieldauto.com (confirmed)

---

## Identification

- No WordPress, no WP plugins, no `admin-ajax.php`
- Scripts loaded from `/lib/jquery/`, `/lib/bootstrap/` (local CDN path — not WordPress)
- Hidden form field `__RequestVerificationToken` present in any form
- Token value starts with `CfDJ8...` (ASP.NET Core Data Protection format)
- Search JS is minimal — just pre-populates dropdowns via GET redirect, actual results require POST

## Anti-Forgery Token Handling

- Token is **session-scoped**, not page-scoped — one `GET` per session is enough
- Extract from: `input[name="__RequestVerificationToken"]`
- Include in every POST as a form field with that exact name
- Using `requests.Session()` ensures cookies are reused across GET → POST

## Search Pattern

- GET `?SelectedMake.Id={id}` → populates model dropdown only, table is empty
- POST with body `SelectedMake={id}&BasicSearch.ModelId=0&...&__RequestVerificationToken={token}` → returns full SSR results
- Must enumerate by make — no "all inventory" endpoint; posting with `SelectedMake=0` returns nothing

## VIN Encoding

- VIN encoded in Bootstrap modal trigger: `data-target="#MAKENAME{VIN}"`
- Extract with: `re.search(r'[A-HJ-NPR-Z0-9]{17}$', data_target).group()`
- Safest to take the trailing 17 chars matching the VIN charset

## Recent Arrivals

- `/newest-cars` returns ~120 most recent vehicles via plain GET — no POST or token needed
- Same SSR table structure as search results

---

## ASP.NET MVC Classic

**Applies to:** sturtevantauto.com (confirmed)

## Identification

- Scripts in `/Scripts/` (e.g. `/Scripts/jquery-3.3.1.js`)
- Bundle paths (`/bundles/jquery` etc.) return 404; actual scripts load fine
- No `__RequestVerificationToken` in forms
- Make/model dropdowns populated via jQuery AJAX to `/Home/GetModels`

## Search Pattern

- POST `/` with `VehicleMake={MAKE}&VehicleModel=` (empty model) → all vehicles for that make in one response, no pagination
- **Empty model = all models for the make** — no need to enumerate models separately
- Makes are listed in the homepage `<select id="car-make">` dropdown

## VIN

- **Not exposed.** Table columns: Year, Make, Model, Color, Reference (engine spec), Stock #, Row, Arrival Date
- No detail page, no hidden VIN field anywhere

## Incremental Runs

- No recent-arrivals endpoint; use the `ARRIVAL DATE` field (MM/DD/YYYY) in each row as a run checkpoint
