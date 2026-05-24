# Pick n Pull San Antonio — Inventory Scraper Strategy

## Site
**URL:** https://picknpullsa.com/vehicle-inventory/

> **Note on "probable duplicate" flag:** This site is NOT a Pull-A-Part location. "Pick n Pull San Antonio" is an independent single-location junkyard unaffiliated with the `pullapart.com` chain. The name is coincidental.

---

## VIN Availability

> ✅ **VIN IS present for every row.** All ~4,542 vehicles in the current inventory have a VIN in the table. VINs for very old/classic vehicles (pre-1981) may be manufacturer serial numbers rather than standard 17-char VINs, but they are still populated.

---

## Location Details

| Field    | Value                                       |
|----------|---------------------------------------------|
| Name     | Pick n Pull San Antonio                     |
| Address  | 11795 Applewhite Rd, San Antonio, TX 78224  |
| Phone    | +1 210-298-5420                             |
| Hours    | Open 7 Days a Week, 8:30am – 5:30pm        |
| Website  | https://picknpullsa.com                     |

Single location only — no multi-yard network.

---

## Inventory Data Format

The inventory is rendered in a standard HTML table with id `vehicles-inventory` at `/vehicle-inventory/`. DataTables is used client-side for sorting/filtering only — there is no AJAX data source. All data is fully present in the raw HTTP response.

**Columns:**

| Column       | Notes                                                        |
|--------------|--------------------------------------------------------------|
| Year         | 4-digit model year                                           |
| Make         | e.g. `CHEVROLET`, `FORD`                                     |
| Model        | e.g. `AVEO`, `F-150`                                         |
| Color        | Free-text color name                                         |
| VIN          | Standard 17-char VIN (pre-1981 vehicles: shorter serial)    |
| Engine       | e.g. `1.6L`, `5.7L`, `4.0L/AT` — empty for some older cars |
| Row          | Yard row number (e.g. `628`, `930`)                         |
| Arrival Date | `MM/DD/YY` format                                            |

**Sample rows:**
```
2010 | CHEVROLET | AVEO          | SILVER   | KL1TD5DE2AB069628 | 1.6L     | 628 | 04/19/23
1992 | CHEVROLET | CAPRICE       | WHITE    | 1G1BL8376NW125315 | 5.7L     | 563 | 10/03/20
2004 | ACURA     | TL            | WHITE    | 19UUA66274A009418 | 3.2L/AT  | 103 | 05/15/26
```

---

## Scraping Strategy

### Pattern: SSR Full Inventory (Single Page, No Auth)

This site follows the **"Simpler Variant — Full Inventory in One SSR Table"** pattern documented in `notes/custom-wp-theme-ssr-inventory.md`.

**Single request retrieves entire inventory:**
```
GET https://picknpullsa.com/vehicle-inventory/
```

- No auth, no cookies, no nonce required
- ~1.87 MB HTML response containing all ~4,500+ rows inline
- Parse `<table id="vehicles-inventory">` → `<tbody>` → `<tr>` rows
- Use BeautifulSoup or Python's `html.parser` for extraction

### Implementation Steps

1. `GET /vehicle-inventory/` with a standard browser `User-Agent` header
2. Parse the HTML using BeautifulSoup (`table#vehicles-inventory tbody tr`)
3. For each `<tr>`, extract `<td>` cells in order: Year, Make, Model, Color, VIN, Engine, Row, Arrival Date
4. Upsert into the common inventory store keyed on VIN
5. Track `Arrival Date` per run — on subsequent runs, compare max arrival date seen previously to identify new additions

### No "New Arrivals" Page

There is no dedicated new-arrivals or recent-additions page. To detect new stock on incremental runs:
- Sort/filter by `Arrival Date` client-side after parsing
- Compare against `last_seen_arrival_date` stored from the prior run
- Any row with `Arrival Date > last_seen_arrival_date` is a new arrival
- Alternatively, compare the full set of VINs against previously persisted records

### Rate Limiting / Politeness

The entire inventory is one page — no loops required. A single GET per run is sufficient. No rate limiting concerns.

### Request Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
```

---

## Notes

- The site runs WordPress with a custom child theme (`avas-child`). DataTables is initialized with `searchPanes` for client-side filtering on Year, Make, Model, Color — no server-side state.
- Page size is ~1.87 MB but loads fast; no Cloudflare or bot protection observed.
- Inventory rows in the 900-series rows (row numbers starting with 9xx) are priced differently according to a site notice — worth flagging in the data.
- Page is `UTF-8`. Some model names contain multi-word values (e.g., `CUSTOM CRUISER`, `PLAIN POST`).
