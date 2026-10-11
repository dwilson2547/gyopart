# junkyard_inventory_scrapers
## Running under scrape-job-manager

Scheduled runs are owned by the scrape-job-manager operator (`web-scrapers/scrape-job-manager` in the
workspace): weekly, Mon–Fri 09:00–19:00 America/New_York, balanced across the week. A scraper joins
the fleet in three steps:

1. **Contract** — wrap `main()` with `scrape_contract.run` and return
   `{"items": total_in_feed, "new": …, "updated": …, "removed": …}`. Raise `scrape_contract.Broken`
   for failures a retry can't fix (selector drift, empty feed, 429). Exit codes: 0 ok, 75 retry,
   65 broken (no retry, counts toward suspension). Record the `ScrapeRun` row as before, then
   re-raise instead of `sys.exit(1)`.
2. **Image** — `<scraper>/Dockerfile` built from this directory (so it can copy
   `scrape_contract.py`), plus a `scraper-<name>` service in the repo-root `docker-compose.yml`:
   `docker compose build scraper-<name> && docker compose push scraper-<name>`, then
   `scripts/pin-scraper-images.sh` to pin the new digest in `helm/gyopart/values-dev.yaml`
   (a changed digest is how the operator knows to retest a suspended job).
   Pin `sqlalchemy>=2.0,<2.1`: 2.1 switches `postgresql://` to psycopg 3, and junkyard-common ships
   psycopg2.
3. **Schedule** — add it under `scraping.scrapers` in `helm/gyopart/values-dev.yaml` (one Scraper
   per yard company, one or more jobs) and push the `dev` branch.

Operate with annotations: `kubectl -n gyopart-dev annotate scrapejob <name>
scrape.danwils.com/run-now=$(date +%s) --overwrite` (or `.../resume=` for a suspended job);
`kubectl -n gyopart-dev get scrapejobs` shows phase, next run and last success.
