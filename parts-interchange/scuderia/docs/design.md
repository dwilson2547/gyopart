# Scuderia OE catalogue → parts_interchange (fleet design)

Status (2026-10-13): **planned**, awaiting review. The collector prototype and its evidence are in
[`../README.md`](../README.md) and [the assessment](../../docs/topics/scuderia-scrape-assessment.md).
Pattern source: parts-direct update scraper v2
([`design-v2.md`](../../parts-direct/update-scraper/docs/design-v2.md)) — queue, discovery, deadline,
sidecar browser and writer conventions are reused rather than re-invented.

## 1. Scope

- **OE diagram catalogues only.** Scuderia's part-finder lists 28 marques / 230 models (✅ counted
  2026-10-13), most of them tuning products. An OE catalogue is a model page offering the `/oe` product
  type (✅ Ferrari 12Cilindri, Aston Martin Cygnet, Rolls-Royce Cullinan have it; Audi R8, BMW 1M, Alfa
  Romeo 4C don't; Mercedes' marque page redirects home). Expected OE marques (user, 2026-10-13): Aston
  Martin, Bentley, Ferrari, Lamborghini, Land Rover, McLaren, Maserati, Rolls-Royce. Discovery decides
  per model from the `/oe` option — no marque list in code — so a marque Scuderia adds later is found.
- Diagram pages only: they carry part number, title, callout, notes and quantity (✅ README). Part detail
  pages are not fetched.
- robots.txt is honoured (the collector refuses disallowed URLs) and the site's 1 s crawl delay is the
  request-auth pacing for its domain.

## 2. Size

| Sample (✅ 2026-10-13) | Variants | Categories | Diagrams |
|---|---:|---:|---:|
| Ferrari 458 | 5 | 2 (Challenge) | 68 (Challenge) |
| Rolls-Royce Cullinan | 1 | 33 | 473 |

⚠ unverified estimate: ~140 OE models × a few variants × 70–500 diagrams ≈ tens of thousands of diagram
pages plus one GIF each. At ~1 request/s with browser overhead that is several days of run time, so the
crawl is a resumable queue worked across daily runs, like parts-direct.

## 3. Discovery and the queue

**Queue unit: one model variant** (`/part-finder/{marque}/{model}/oe/{variant_id}`) — the equivalent of a
parts-direct vehicle, and the unit that becomes a car (§4). A variant is 70–500 diagram pages; the
mid-vehicle deadline stop and webcache (pages are cached as fetched) make a variant interrupted at the
deadline cheap to resume.

- **Queue table: `scrape_target`, unchanged** — `work_queue.py`'s claim/lease/release/mark functions are
  reused as they are. A variant row: `manufacturer_id` (§4), `make` = marque slug, `model` = model slug,
  `trim` = variant id, `year` = `''` (the column is NOT NULL; years come from the variant name at write
  time), `engine` NULL, `page_url` = the variant URL. ✅ built 2026-10-14: `discovery.py`. Statuses as parts-direct
  (`pending`/`done`/`no_catalog`/`failed`).
- **Discovery** (monthly, `discovery_interval_days`): part-finder → each marque → each model; a model with
  an `/oe` product type → its variant list → upsert each variant. ~230 model pages + variant pages per
  pass. Categories and diagrams are listed by the crawl itself (the collector already walks
  variant → category → diagram).
- **Crawl of one variant:** variant page → each category → each diagram page, parsed by the existing
  `catalog.parse_catalog` (selector-drift checks included) → diagram GIFs to imgcache → one DB
  transaction (§5) → mark `done`. The JSONL journal is dropped in the fleet job: webcache holds every page
  and the DB is the record (the collector CLI keeps it for ad-hoc runs).

## 4. Mapping to parts_interchange

- **Manufacturer: one row per marque** (Ferrari, Lamborghini, …), so part numbers stay per brand under
  `uq_part_manufacturer_number`; found by `lower(name)` = the marque's display name. Discovery skips an
  OE marque that has no manufacturer row and logs it, so a new marque is added deliberately.
- **Land Rover is out of this set** (user, 2026-10-14): parts-direct's `jaguar` site already covers it.
- **Car = variant.** make = marque display name, model = model name, trim = variant name, engine NULL.
  - Variant name carries a year range (Rolls-Royce: `Cullinan RR31(2017-2023)`, ✅) → one car per model
    year, all linked to the variant's diagrams through `car_diagrams` (many-to-many, ✅ schema), matching
    gyopart's per-year cars so yard vehicles can resolve against them.
  - No year range (Ferrari: `458 Italia`, ✅) → one car with `year_id` NULL (`uq_car_vehicle` treats NULLs
    as equal, ✅ schema). ⚠ Yard matching needs a year, so these cars serve part lookups but not VIN/YMM
    resolution until a year source is found (user, 2026-10-14: fine for now; finding one is a follow-up).
- **Category / subcategory:** Scuderia category → `category`, diagram title → `subcategory`, both upserted
  by name (existing unique keys).
- **Parts:** upsert on (manufacturer, part_number); title from the row; `url` = the site part URL.
- **Images:** `image` (manufacturer, name = GIF filename) with `imgcache_hash` / `imgcache_bucket`
  (`scuderia`), as parts-direct records them.

## 5. Writer (one transaction per variant)

- **Collapse duplicate rows** (user, 2026-10-13): `diagram_parts` is one row per (diagram, part) (✅
  primary key). Rows for the same part on one diagram merge; `part_index` = its distinct callouts joined
  `", "` in page order (✅ longest seen in the 3 samples: 8 chars of 25; truncate at the last whole callout
  if ever longer). Sample: Ferrari 458 crankcase 69 rows → 61 parts, McLaren 12C 27 → 26.
- **Notes join** (user, 2026-10-13): distinct non-empty row notes for a part are joined `"; "` into
  `part.notes` (e.g. Ferrari 278162: "Not for EU GS, UK" / "Lead free; Applicable for EU GS, UK; …"),
  merged with notes already stored for that part so other diagrams' notes are kept.
- Quantity on diagram, price and stock are not stored (no columns); hotspot geometry is not stored.
- The variant's cars get `car_parts` = the union of its diagrams' parts; its diagrams are replaced on
  re-scrape, like parts-direct's writer.

## 6. Running it

- **Image** `gyopart-scraper-scuderia`, built from `parts-interchange/scuderia/`, run by
  scrape-job-manager as one ScrapeJob (`scraping.browserSidecar: true` — it drives the browser for every
  page), headed browserless 2.57 through the VPN proxy (✅ cluster smoke 2026-10-13: 3 diagrams / 107 rows
  through the shared 2.57 service and the VPN, no challenge help).
- Exit codes, deadline stop (between and within variants) and stop conditions as parts-direct: challenge
  unresolved / 403 / 429 → stop 65 or 75, selector drift → fail the variant, 5 in a row → stop.
- request-auth: `www.scuderiacarparts.com` paced at ≥ 1 s.
- Dev first (dev parts DB, `scuderia` bucket), a full Ferrari pass checked by hand, then prod.

## 7. Build order

1. Discovery + queue (variants into `scrape_target`), run once in dev to size the catalogue for real.
2. Variant crawl + writer, tests from captured pages (the existing 69-row Ferrari fixture plus a
   Rolls-Royce one for the year-range path).
3. Image, compose service, dev ScrapeJob with sidecar; manufacturer rows inserted by the user.
4. Prod after a clean dev Ferrari pass.

## 8. Open

- A year source for variants without a range (§4).

Decided 2026-10-14 (user): Land Rover excluded (§4); year-less cars acceptable for now; the job runs in
the default parts-direct pool and run length, so the backfill spreads over daily runs.
