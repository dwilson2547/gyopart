# Mopar scrape cached 503 maintenance pages and marked 3,492 vehicles done

**Date:** 2026-10-11 · **Status:** open — affected vehicles need re-scraping

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

## Impact

- gyopart-dev holds the Mopar load as generated (manufacturer id 22, makes 34–38, cars from id
  43040, parts from 2664754, images from 5909731, diagrams from 8522737); prod does not.
- Modern Chrysler/Dodge/Jeep/Ram/Fiat appear in the picker with no parts.

## Fix needed

1. The scraper must treat a maintenance/5xx page as a failed fetch: don't cache it, don't mark the
   vehicle done, retry later. Same rule belongs in any updater and in the scrape-stack caching path,
   which would otherwise serve the error page from cache on every retry.
2. Re-scrape the 3,492 vehicles (reset `done` for nodes whose cached page is the 503 page), then
   regenerate and reload the Mopar CSVs.
