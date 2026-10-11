# Mopar scrape cached 503 maintenance pages and marked 3,492 vehicles done

**Date:** 2026-10-11 · **Status:** partially resolved — 739 vehicles loaded; 3,492 await the update scraper

## Symptom

Loading the Mopar catalogue (`parts-direct-data/fiat/`, site moparpartsproonline.com, loader config
`fiat`) into gyopart-dev added 6,528 cars, but only 739 had any parts or diagrams. A 2015 Jeep
Wrangler walked through the vehicle picker fine and then showed 0 parts.

## Cause

Every vehicle in `tree.json` is `done: true`, but for 3,492 of them the cached landing page in
`webcache/` is the site's **"503 Service Under Maintenance"** page. The scraper stored the error
page, found no category links on it, and recorded the vehicle as finished with empty
`parts`/`diagrams`. The site was evidently down while those vehicles were reached.

Cached landing pages of the 5,789 vehicles with no parts (measured 2026-10-11):

| Cached page | Vehicles | Years |
|---|---|---|
| 503 maintenance page | 3,492 | all of 2007 and 2010–2024; part of 2006, 2008, 2009 |
| real "Select Parts Category" page with no categories | 2,296 | all of 1984–2000; a few dozen per year 2001–2006 — genuinely no catalogue |
| other | 1 | 2007 |

The webcache cannot fill the gap: for the 503 vehicles only the landing page was ever fetched, so
re-parsing the cache recovers nothing.

## Real maintenance windows, not a block

The site serves the 2015 Wrangler's categories normally today (checked by the user, 2026-10-11).
Cache-file timestamps of the landing pages show two maintenance bursts, both starting just after
midnight (NFS server local time):

| Window | 503 pages | Then |
|---|---|---|
| 2024-09-09 00:23–00:41 | 215 (2006–2008) | site back; normal scraping for a week |
| 2024-09-16 00:12–04:53 | 3,277 (2009–2024) | scraper reached the end of the tree and stopped |

A real vehicle took the scraper from about 30 minutes to several hours (deep crawl of categories and
diagrams); a maintenance page took seconds. Once the site went down, every remaining vehicle was
"finished" almost instantly. Scraping resumed normally after the first window, which rules out a
bot block.

So, beyond not caching the page: a maintenance/5xx page must **stop the run** as transient (exit 75
under scrape-job-manager) instead of moving on, and scheduled runs should stay out of the night window
(the business-hours pool already does).

## Impact and what was loaded (2026-10-11)

- Prod and dev both hold the Mopar catalogue for the **739 vehicles that have parts** (manufacturer
  id 22 `Fiat`, makes 34–38, parts from id 2664754, images from 5909731, diagrams from 8522737). The
  5,789 vehicles with no parts were left out of prod and deleted from dev, so the picker never offers
  a vehicle with nothing behind it; dev and prod row counts match on all 19 tables.
- Their make/model/trim/engine rows were kept, for the update scraper to reuse.
- Plan (user, 2026-10-11): the update scraper fills in the 3,492 maintenance-page vehicles by creating
  DB records as it scrapes — the move away from bulk loads.

## Fix needed

1. The scraper must treat a maintenance/5xx page as a failed fetch: don't cache it, don't mark the
   vehicle done, retry later. Same rule belongs in any updater and in the scrape-stack caching path,
   which would otherwise serve the error page from cache on every retry.
2. Re-scrape the 3,492 vehicles (reset `done` for nodes whose cached page is the 503 page), then
   regenerate and reload the Mopar CSVs.
