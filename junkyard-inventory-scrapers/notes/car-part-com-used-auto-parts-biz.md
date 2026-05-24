# Car-Part.com White-Label Retail Search (`used-auto-parts.biz`)

**Applies to:** mcdonoughautoparts.com (confirmed — member ID 2191)

---

## Identification

- Inventory Search nav link points to `http://search{MEMBER_ID}.used-auto-parts.biz/inventory/retail.htm`
- Static HTML page with a CGI form; no JS required to render the search UI
- Form action: `/cgi-bin/search.cgi` (POST)
- Footer: `© 1998–{year} Car-Part.com`
- Logo: `/InvLogo.gif` (blank/yard-branded)

## Why It Cannot Be Scraped for Vehicle Inventory

- **Parts-centric search only:** Requires Year + Make/Model + Part type (all mandatory). No "all vehicles" endpoint.
- **~1,670 make/model options × years × ~250 part types** = O(millions) of requests to enumerate all inventory
- **Stateful session IDs:** First POST generates a short-lived `sessionID`. Second POST uses it to retrieve results. IDs are single-use — replaying returns HTTP 500.
- **No VINs exposed:** Results show stock#, part desc, price, condition. No VIN in any response.
- **Car-Part.com owns and hosts the data:** ToS prohibits scraping. The `{ID}.used-auto-parts.biz` domain is Car-Part.com infrastructure, not the yard's own server.

## Member ID Location

- Member ID is embedded in the subdomain: `search2191.used-auto-parts.biz` → member `2191`
- Can cross-reference against Car-Part.com's public member directory if needed

## Recommended Action

**Skip all sites using this platform.** No feasible path to vehicle-level inventory extraction. Document findings and move on.
