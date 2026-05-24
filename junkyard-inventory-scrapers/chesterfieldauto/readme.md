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

### Full Inventory (Search by Make)

Results are only returned via **POST**. GET requests pre-populate the model dropdown but return an empty table.

**Step 1 — Get token + make list:**

```
GET /search-our-inventory-by-location
```

Extract from the HTML:
- `__RequestVerificationToken` from the hidden input: `input[name="__RequestVerificationToken"]`
- All make options from `select#selected-make`: each `<option>` has a numeric `value` and a text name

**Step 2 — For each make ID, POST:**

```
POST /search-our-inventory-by-location?SelectedMake.Id={makeId}
Content-Type: application/x-www-form-urlencoded

SelectedMake={makeId}&BasicSearch.ModelId=0&BasicSearch.BeginYear=&BasicSearch.EndYear=&__RequestVerificationToken={token}
```

- `BasicSearch.ModelId=0` means all models
- Year fields can be empty for no year filter
- The `__RequestVerificationToken` is valid across all POSTs in the same session (not per-page)

**Step 3 — Parse the SSR response HTML:**

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

**Pagination:** None. All matching vehicles are returned in a single response per make.

### No Dump-All Endpoint

Posting with `SelectedMake=0` (no make filter) returns 0 results — the server requires a valid make selection. You must enumerate by make.

There are ~70 makes in the dropdown. Most will return "Sorry, there aren't any matches in our current yard vehicle inventory." Only ~10-20 common makes will have inventory.

### Recent Arrivals (Delta Check)

```
GET /newest-cars
```

- Pure SSR, no POST or token required
- Returns the ~120 most recently added vehicles across all 3 yards
- Same table structure and VIN extraction method as search results
- Sorted by arrival date descending
- Useful as a delta check: if all VINs in this page were seen in the previous run, inventory has not changed significantly

---

## Additional Data (Modal)

Clicking "Pics" opens a Bootstrap modal. Each modal's `id` matches its button's `data-target` (without the `#`). The modal HTML (rendered server-side in the initial page load) contains:

- **Stock Number** — `000000076840` format (internal YMS ID)
- **Transmission** — e.g. "Automatic"
- **Drive** — e.g. "4WD/4-Wheel Drive/4x4"
- **Photos** — from `api.yardsmartapp.com/rails/active_storage/...`

These fields are already in the page HTML — no additional HTTP request is needed to fetch them. Parse `div[id="{make}{vin}"]` for each vehicle.

---

## Python Scraper Outline (`requests`)

```python
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://chesterfieldauto.com"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 ..."})

def get_token_and_makes():
    r = SESSION.get(f"{BASE_URL}/search-our-inventory-by-location")
    soup = BeautifulSoup(r.text, "html.parser")
    token = soup.find("input", {"name": "__RequestVerificationToken"})["value"]
    makes = [
        {"id": o["value"], "name": o.text.strip()}
        for o in soup.select("select#selected-make option")
        if o["value"] != "0"
    ]
    return token, makes

def search_make(make_id, token):
    r = SESSION.post(
        f"{BASE_URL}/search-our-inventory-by-location?SelectedMake.Id={make_id}",
        data={
            "SelectedMake": make_id,
            "BasicSearch.ModelId": "0",
            "BasicSearch.BeginYear": "",
            "BasicSearch.EndYear": "",
            "__RequestVerificationToken": token,
        },
    )
    return parse_results(r.text)

def parse_results(html):
    soup = BeautifulSoup(html, "html.parser")
    vehicles = []
    for row in soup.select("table tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 10:
            continue
        btn = cells[0].find("button", {"data-target": True})
        vin_match = re.search(r"[A-HJ-NPR-Z0-9]{17}$", btn["data-target"]) if btn else None
        vehicles.append({
            "vin": vin_match.group() if vin_match else None,
            "store": cells[1].text.strip(),
            "make": cells[2].text.strip(),
            "model": cells[3].text.strip(),
            "year": cells[4].text.strip(),
            "color": cells[5].text.strip(),
            "body": cells[6].text.strip(),
            "engine": cells[7].text.strip(),
            "yard_row": cells[8].text.strip(),
            "date_set": cells[9].text.strip(),
        })
    return vehicles

def get_newest():
    r = SESSION.get(f"{BASE_URL}/newest-cars")
    return parse_results(r.text)
```

The `__RequestVerificationToken` is session-scoped in ASP.NET Core (not per-page), so one GET is enough per scrape session — no need to re-fetch the token for every make.

---

## Notes

- The token needs to be extracted once per session; it remains valid for all subsequent POSTs within that session.
- There is no location filter — all 3 yards always appear in results. The `Store` column identifies which yard each vehicle is in.
- The "Set" date is the date the car was pulled into the yard, not a purchase date.
- One vehicle had a missing VIN in the newest-cars page (119/120 had VINs) — handle `None` gracefully.
- The `Yard Row` column (e.g. "Import 15 K", "GM 34 D") encodes the physical location in the yard by section and row — useful for pickers.
