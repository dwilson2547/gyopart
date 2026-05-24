# McDonough Used Auto Parts — Inventory Scrape Assessment

> **⚠️ NOT A VIABLE SCRAPE TARGET**
>
> The `/used-vehicle-gallery` page is a stale static photo gallery (12 vehicles from 2021, last updated ~2021) with **NO VINs** and no structured inventory data. The actual inventory system is hosted on Car-Part.com's platform (`search2191.used-auto-parts.biz`), which is a parts-search service — not a vehicle inventory system — and is not feasibly scrapable for full vehicle inventory.

---

## Site Overview

**URL:** https://www.mcdonoughautoparts.com/used-vehicle-gallery  
**Platform:** Hibu website builder (hibuwebsites.com CDN)  
**Inventory platform:** Car-Part.com white-label (`search2191.used-auto-parts.biz`)  
**Car-Part.com Member ID:** 2191  
**Locations:** 3 (McDonough, Forsyth, Covington — all in Georgia)  
**Member of:** Georgia Auto Recyclers Association, URG - United Recyclers Group

---

## Locations

| Location | Address | Phone | Toll-Free | Fax | Notes |
|---|---|---|---|---|---|
| McDonough (HQ / Truck yard) | 942 Highway 42 N, McDonough, GA 30253 | 770-957-9808 | 1-888-216-4740 | 770-898-4800 | Ford, Chev, Dodge Trucks Only |
| Forsyth | 129 Town Creek Rd., Forsyth, GA 31029 | 478-992-9934 | 1-866-992-9934 | 478-992-9354 | — |
| Covington | 4848 Hwy 162 S, Covington, GA 30016 | 678-729-9940 | 1-855-430-8934 | 678-561-9941 | — |

**Email (all locations):** sales@mcdonoughautoparts.com  
**Language:** Se Habla Español

---

## The `/used-vehicle-gallery` Page — Findings

- Hosted on **Hibu** website builder; no CMS inventory plugin
- Rendered as a series of photo carousels (Hibu `<ul>` slide modules) — one carousel group per vehicle
- Each vehicle carousel has: a `<p class="rteBlock">` with minimal text like `2007 Chev Tahoe stk#21I006`
- **Only 12 vehicles found** (confirmed with DOM inspection)
- **Stock number format:** `21I006`, `21H159` — prefix encodes year (21 = 2021) and possibly location
- **NO VINs** present anywhere on the page
- Gallery appears to be manually curated notable/interesting arrivals — not a live inventory feed
- Data is stale: all 12 entries have 2021 stock number prefixes; gallery has not been updated since ~2021

### Vehicles on the Gallery (as of investigation date)
```
2007 Chev Tahoe          stk#21I006
2011 Dodge Durango       Stock #21I004
2005 Ford F-150          stk#21I003
2011 Hyundai Sonata GLS  stk#21I005
2011 GMC Terrain SLT     stk#21I014
2008 Silverado 1500      stk#21H159
2014 Cadillac ATS        stk#21H150
2017 Chev Malibu LS      Stk#21H132
2013 Ram 1500 SLT        stk#21H129
2009 GMC Yukon Denali    stk#21H108
2017 Hyundai Sonata SE   stk#21H149
2013 Jaguar XF           stk#21H140
```

---

## The Actual Inventory System — Car-Part.com Platform

The "Inventory Search" nav link routes to: `http://search2191.used-auto-parts.biz/inventory/retail.htm`

### Platform Identification
- URL pattern: `search{MEMBER_ID}.used-auto-parts.biz` — Car-Part.com white-label retail search
- Member ID: **2191**
- CGI-based legacy web application; form posts to `/cgi-bin/search.cgi`
- Search **requires** specifying: Year + Make/Model + Part type (all three are mandatory)
- No "all vehicles" or "browse all inventory" endpoint exists

### Why Full Inventory Scraping Is Not Feasible

1. **Parts-centric, not vehicle-centric:** The system is designed for parts lookup, not vehicle inventory. Each query returns parts available for a specific vehicle × part type combination.
2. **Mandatory tri-filter:** Year (1950–2026), Make/Model (~1,670 combinations), Part type (~250 options) — all required. To enumerate all vehicles would require O(years × models × parts) requests = millions of queries.
3. **Stateful session IDs:** The first POST to `/cgi-bin/search.cgi` generates a session-scoped `sessionID`. The actual results page is a second form submission using that session ID. Sessions appear to be short-lived and tied to the originating connection.
4. **No VINs in results:** Test searches confirmed no VINs are returned. The platform shows: stock number, part condition, price, description, and yard location.
5. **Car-Part.com ToS:** Car-Part.com explicitly prohibits scraping their platform. The `{MEMBER_ID}.used-auto-parts.biz` domain is hosted and controlled by Car-Part.com, not the yard.
6. **Server error on replay:** Replaying session ID POST requests returns HTTP 500 from Apache — IDs are single-use.

### What Car-Part.com Does Expose
- Yard name, phone, location (implicit in member ID)
- Part listings with: stock#, year, make/model, part description, price, condition
- No VIN, no vehicle-level inventory enumeration

---

## Conclusion

**This site is NOT a viable inventory scrape target.** The reasons:

1. The linked page (`/used-vehicle-gallery`) is a manually-maintained photo gallery of ~12 vehicles from 2021 — effectively a marketing page, not inventory
2. The actual inventory lives on Car-Part.com's platform, which:
   - Requires exhaustive enumeration (millions of requests) to obtain full inventory
   - Does not expose VINs
   - Is governed by Car-Part.com's ToS, which prohibits scraping
3. There is no dedicated recent-arrivals page or any streaming/feed mechanism for new vehicles

**Recommendation:** Skip this site. If McDonough inventory is needed in the future, contact them directly for a data export or monitor their Car-Part.com listing via Car-Part.com's legitimate API channels (if available).

---

## Notes on Car-Part.com Platform Pattern

- Other yards using `search{ID}.used-auto-parts.biz` will have the same constraints
- The member ID is in the subdomain; cross-reference against Car-Part.com's member directory if needed
- All such sites require Year + Make + Part for any query — no bulk inventory access
- Session IDs are one-time use and short-lived — replay-based scraping will not work
