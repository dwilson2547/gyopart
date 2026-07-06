# TODO

Backlog imported from the retired todo store, 2026-07-06.

## Urgent

- [ ] **Build a parser for Ducati parts PDFs** — Create a Ducati parts parser that works on scanned or image-based PDFs because the current parser only handles text-based documents.

## High

- [ ] **Add DB write path to parts-direct updater** — Wire parts_interchange DB writes into updater.py so scraped data lands in Postgres in one pass. Covers Vehicle, Part, diagram, and fitment records. Architecture decision: scraper writes cache + DB together, no separate loader for new runs. Related: context-store: gyopart/issues/parts-direct-picker-ajax-get-csrf, notes #16 (phase status), master plan at parts-interchange/docs/superpowers/plans/2026-05-17-parts-interchange-master-plan.md.
- [ ] **Validate update-scraper fix against Mopar sites** — Figure out whether the update-scraper fix we made also works correctly on the Mopar sites before rolling it out more broadly.
- [ ] **Regression-test Lexus update-scraper fix across other makes** — Make sure the Lexus-specific update-scraper fix did not break the updater flow for the other makes. Cross-check against the broader updater work as needed.
- [ ] **Add monitoring coverage for gyopart** — Review the current gyopart monitoring gap and add the missing observability pieces so the production stack is no longer under-monitored.
- [ ] **Add junkyard inventory scraper CronJobs to Helm** — Set up the CronJobs for the junkyard inventory scrapers in Kubernetes and add the deployment wiring to the Helm chart.
- [ ] **Build a motorcycle parts interchange system** — Create the parts interchange system for the motorcycle parts data, including the core modeling and workflow decisions.
- [ ] **Map Ducati superseded part numbers in the scraper** — Write a Ducati scraper flow that detects chained part-number replacements and records mappings so superseded part numbers resolve as the same interchange part.

## Medium

- [ ] **Deploy gyopart production stack** — Bring up the production gyopart deployment using the existing Helm and cluster patterns from the gyopart stack.
- [ ] **Expose VinCache data in the gyopart admin experience** — Extend the admin-facing experience to make VinCache data inspectable, either in the current admin interface or wherever it fits best.
- [ ] **Extend gyopart API and UI functionality** — Review the current gyopart API and UI end-to-end and add the next round of missing functionality and quality-of-life improvements.
- [ ] **Explore a standalone parts-interchange interface on gyopart data** — Consider building a separate parts-interchange API/UI that uses the same underlying data as gyopart so workflows can be compared and potentially swapped later.
- [ ] **Deploy update-scraper to Helm after DB-write stabilization** — Once update-scraper bugs are fixed and it writes directly to the database reliably, add Helm deployments for each make.
- [ ] **Clean up junk code in the gyopart repo** — Go through the gyopart repository and remove stale or junk code paths so the tree is easier to reason about.
- [ ] **Run motorcycle scrapers in Kubernetes with admin services** — Update the motorcycle scrapers to run in Kubernetes and add the associated admin/API-style services needed to operate them.
- [ ] **Build a framework for general document scrapers** — Create a reusable scraper system for document-centric scrapers such as the Ducati owners manual scraper.
- [ ] **Explore local LLM rule generation for gyopart admin-api** — Experiment with a local LLM connected to the gyopart admin-api to automatically create rules that resolve mapping discrepancies.
- [ ] **Evaluate RockAuto-style external parts reference scraping** — Consider scraping an external parts reference such as RockAuto to find parts interchangeable across manufacturers, but first collapse vehicles into distinct canonical car configurations so equivalent generations/configs are only scraped once instead of re-querying every model year.
