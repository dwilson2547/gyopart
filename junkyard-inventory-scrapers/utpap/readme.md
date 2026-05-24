# Utah Pic-A-Part — utpap.com

## Locations

### Ogden

| Field   | Value |
|---------|-------|
| Name    | Utah Pic-A-Part Ogden |
| Address | 555 W. 17th Street, Ogden, UT 84404 |
| Phone   | (801) 612-6446 |
| Hours   | Mon–Sat 8:00 am – 4:30 pm, Sun 9:00 am – 4:00 pm |
| Social  | [Facebook](https://www.facebook.com/UTPAPOGDEN/) · [Instagram](https://www.instagram.com/utpap_ogden/) |

### Orem

| Field   | Value |
|---------|-------|
| Name    | Utah Pic-A-Part Orem |
| Address | 255 S. Geneva Road, Orem, UT 84058 |
| Phone   | (801) 756-5878 |
| Hours   | Mon–Sat 8:00 am – 5:00 pm, Sun 8:00 am – 4:30 pm |
| Social  | [Facebook](https://www.facebook.com/p/Utah-Pic-A-Part-Orem-100069411191663/) · [Instagram](https://www.instagram.com/utahpicapartorem/) |

---

## Platform

**CrushYMS** — same XML-feed strategy as `us_auto_parts_sterling_heights` and other CrushYMS yards.  
Front-end widget is **VinPlus / TexnRewards** (vinplus.texnrewards.com), served via iframe on both inventory pages.  
See notes: [crushyms-xml-feed-via-saas-config-leak.md](../notes/crushyms-xml-feed-via-saas-config-leak.md)

The VinPlus admin config endpoint is unauthenticated and leaks the raw XML feed URLs:

```
GET https://inventory-search-api-581547763015.us-central1.run.app/api/admin/yard-config/utah_pic_a_part
```

---

## VIN Availability

**VINs are present for all vehicles in both feeds.**  
- Orem: 674 vehicles, 674 VINs (100%)  
- Ogden: 974 vehicles, 974 VINs (100%)

---

## Inventory Strategy

### Preferred: Direct XML Feed (CrushYMS)

Two unauthenticated XML feeds, one per location. A single `GET` request per location yields the **complete inventory** including VINs, colors, mileage, arrival dates, and yard row numbers.

| Location | Client ID | Feed URL |
|----------|-----------|----------|
| Orem     | 1065      | `http://45.79.157.162/1065_inventory.xml` |
| Ogden    | 1064      | `http://45.79.157.162/1064_inventory.xml` |

> **Note:** Feed URLs are on plain HTTP. Fetch from a server-side scraper (not a browser) to avoid mixed-content restrictions.

### XML Feed Structure

Root: `<INVENTORY>`, children: `<ASSET>`

| Field | Description |
|-------|-------------|
| `STOCKNUMBER` | Yard stock number — use as dedup key (e.g. `K038514`) |
| `VIN` | Full 17-char VIN |
| `iYEAR` | Model year |
| `MAKE` | Make (e.g. `FORD`) |
| `MODEL` | Model (e.g. `FUSION`) |
| `COLOR` | Exterior color |
| `MILEAGE` | Odometer (note: many entries show `1` — likely a placeholder) |
| `YARD_IN_DATE` | Arrival timestamp (ISO 8601 with ms, e.g. `2026-05-18T11:20:00.677`) |
| `VEHICLE_ROW` | Physical row in yard |
| `LOCATION` | Always `YARD` in active feeds |
| `iSTATUS` | `0` = active/in-yard |
| `LASTUPDATE` | Last YMS modification timestamp |
| `HOL_MODEL` | Holander model string (e.g. `FORD F150 PICKUP`) |
| `REFERENCE` | Engine reference (often empty) |
| `YARD_NAME` | e.g. `UTAH PIC-A-PART OREM` |
| `YARD_CITY` / `YARD_STATE` | Location city/state from the feed itself |

### Sample Scraper

```python
import requests
import xml.etree.ElementTree as ET

FEEDS = {
    "orem": "http://45.79.157.162/1065_inventory.xml",
    "ogden": "http://45.79.157.162/1064_inventory.xml",
}

def scrape_location(location_name: str, url: str) -> list[dict]:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    records = []
    for asset in root.findall("ASSET"):
        records.append({
            "location":    location_name,
            "stock":       asset.findtext("STOCKNUMBER"),
            "vin":         asset.findtext("VIN"),
            "year":        asset.findtext("iYEAR"),
            "make":        asset.findtext("MAKE"),
            "model":       asset.findtext("MODEL"),
            "color":       asset.findtext("COLOR"),
            "mileage":     asset.findtext("MILEAGE"),
            "row":         asset.findtext("VEHICLE_ROW"),
            "date_in":     asset.findtext("YARD_IN_DATE"),
            "status":      asset.findtext("iSTATUS"),
            "last_update": asset.findtext("LASTUPDATE"),
            "hol_model":   asset.findtext("HOL_MODEL"),
        })
    return records

all_inventory = []
for loc, url in FEEDS.items():
    all_inventory.extend(scrape_location(loc, url))
```

---

## Recent Arrivals / Delta Detection

There is no dedicated recent-arrivals page with useful data (the `/new-arrivals/` WordPress page exists but contains no inventory content).

**Use `YARD_IN_DATE` from the XML feed** for delta detection:

1. On each run, fetch both feeds.
2. Compare `STOCKNUMBER` values against your stored set.
3. New STOCKNUMBERs = new arrivals. Missing STOCKNUMBERs = pulled/removed.
4. Sort new arrivals by `YARD_IN_DATE` descending to identify the most recently set vehicles.

The feed is regenerated daily (process time: 02:00 MT for Orem, 06:00 MT for Ogden based on the yard config).

---

## Public Inventory Pages (SSR HTML — Fallback Only)

The website also exposes SSR HTML inventory pages accessible via GET params. These do **not** include VINs, colors, or mileage — only Year, Make, Model, Stock#, Engine, Vehicle Row, and Date Set. Use the XML feed instead.

| Location | Iframe URL |
|----------|-----------|
| Orem     | `https://utpap.com/search-inventory_orem.php?make=FORD&model=` |
| Ogden    | `https://utpap.com/search-inventory_ogden.php?make=FORD&model=` |

- Make is **required** — omitting it returns an empty table.
- Model is optional; pass empty string for all models of a make.
- The `modelMap` JS object embedded in each PHP page lists all available make/model combinations per location.

---

## Photo URL Pattern

Vehicle photos referenced in the HTML inventory follow:

```
https://utpap.com/Orem-inventory-photos/{STOCKNUMBER}.jpeg
https://utpap.com/Ogden-inventory-photos/{STOCKNUMBER}.jpeg
```
