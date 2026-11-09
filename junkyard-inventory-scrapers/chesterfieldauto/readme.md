# Chesterfield Auto Parts — Inventory Scraping Strategy

**Site:** https://chesterfieldauto.com/search-our-inventory-by-location  
**Recent Arrivals:** https://chesterfieldauto.com/newest-cars  
**Researched:** 2026-05-18  

---

## Locations (3 Yards)

| Yard | Address | Phone | Hours |
|------|---------|-------|-------|
| Richmond Yard | 5111 Old Midlothian Tpke, Richmond, VA 23224 | (804) 233-5481 | M-Th 9am–5pm, F-Su 8am–5pm |
| Ft. Lee Yard | 4855 Puddledock Rd, Prince George, VA 23875 | (804) 732-9253 | M-Th 9am–5pm, F-Su 8am–5pm |
| Southside Yard | 12910 Genito Rd, Midlothian, VA 23112 | (804) 744-0716 | M-Th 9am–5pm, F-Su 8am–5pm |

All 3 yards are covered in every search response. The `Store` column in results maps to "Richmond", "Fort Lee", or "Southside".

---

## VIN Availability

**VIN is available.** It is embedded in the `data-target` attribute of the "Pics" button for every row:

```html
<button data-target="#HONDA1HGCA5548HA212333">Pics</button>
```

The format is `#{MAKE_UPPERCASE}{17-CHAR-VIN}`. Extract the VIN by taking the last 17 characters of the `data-target` value (after stripping the leading `#`), or use a regex:

```python
import re
target = "#HONDA1HGCA5548HA212333"
vin_match = re.search(r'[A-HJ-NPR-Z0-9]{17}$', target)
vin = vin_match.group() if vin_match else None
# -> "1HGCA5548HA212333"
```

---

## Platform

Custom **ASP.NET Core MVC** site — not WordPress, not a known junkyard SaaS. It uses the `__RequestVerificationToken` anti-forgery pattern standard to ASP.NET Core. Vehicle images are hosted externally on `api.yardsmartapp.com` (Rails Active Storage), but YardSmart does not appear to expose a public API — the inventory is served SSR by the main site only.

---

## Inventory Access Strategy

### Full Inventory (Search by Make + Model)

Results are only returned via **POST**. Since ~2026-10 the search requires a model: `ModelId=0`
(formerly "all models") and an empty year range both return nothing. The model lists are a
catalogue (Chevrolet 129, Ford 150), so a full crawl is ~2,500 searches, most of them empty.

**Step 1 — Get token + make list:** `GET /search-our-inventory-by-location`. Extract
`input[name="__RequestVerificationToken"]` and the numeric `value` of each `select#selected-make`
option. One token serves every POST in the session.

**Step 2 — Models per make:** `GET /search-our-inventory-by-location?SelectedMake.Id={makeId}`. The
server renders that make's models into `select#selected-model` (numeric `value`s).

**Step 3 — For each make + model, POST:**

```
POST /search-our-inventory-by-location?SelectedMake.Id={makeId}
Content-Type: application/x-www-form-urlencoded

SelectedMake={makeId}&BasicSearch.ModelId={modelId}&BasicSearch.BeginYear=1900&BasicSearch.EndYear=2100&__RequestVerificationToken={token}
```

The scraper reuses model lists and empty results from the webcache for a week, so a daily run
re-searches only models that had stock; a car arriving under an empty model can take a week to appear.

**Step 4 — Parse the SSR response HTML:**

Results are in `table tbody tr`. Each row has 10 `<td>` cells:

| Index | Column | Notes |
|-------|--------|-------|
| 0 | Pics (button) | Contains `data-target="#MAKE{VIN}"` |
| 1 | Store | "Richmond", "Fort Lee", or "Southside" |
| 2 | Make | Uppercase make name |
| 3 | Model | |
| 4 | Year | |
| 5 | Color | May be empty |
| 6 | Body | e.g. "Sedan", "SUV", "Pickup" |
| 7 | Engine | e.g. "2.3L 4cyl", may be empty |
| 8 | Yard Row | e.g. "Import 15 K", "GM 34 D" |
| 9 | Set | Date added to yard (M/D/YYYY) |

The VIN is in the `<button data-target>` in `td[0]` — not a visible column.

**Result count:** `GET` the body text for `N vehicle records found` to check counts before parsing.

**Pagination:** None. All matching vehicles are returned in a single response per search.

### Recent Arrivals (Delta Check)

```
GET /newest-cars
```

- Pure SSR, no POST or token required
- Returns the ~120 most recently added vehicles across all 3 yards (about two days of arrivals, 2026-10)
- Same table structure and VIN extraction method as search results
- Sorted by arrival date descending
- Useful as a delta check: if all VINs in this page were seen in the previous run, inventory has not changed significantly

---

## Additional Data (Modal)

Each row's "Pics" button opens a Bootstrap modal rendered in the same response; its `id` is the
button's `data-target` without the `#` (`{MAKE}{VIN}`). Markup as of 2026-10:

- `h5.modal-title` — `Images for Stock# 000000083593` (stock number, internal YMS ID)
- `h6` lines — `Transmission: Automatic`, `Drive: FWD/Front-Wheel Drive`
- `img.yard-veh-img` — photos from `api.yardsmartapp.com/rails/active_storage/...`; the first is
  stored as the vehicle's preview image

Implementation: `scraper.py`.

---

## Notes

- The token needs to be extracted once per session; it remains valid for all subsequent POSTs within that session.
- There is no location filter — all 3 yards always appear in results. The `Store` column identifies which yard each vehicle is in.
- The "Set" date is the date the car was pulled into the yard, not a purchase date.
- One vehicle had a missing VIN in the newest-cars page (119/120 had VINs) — handle `None` gracefully.
- The `Yard Row` column (e.g. "Import 15 K", "GM 34 D") encodes the physical location in the yard by section and row — useful for pickers.
