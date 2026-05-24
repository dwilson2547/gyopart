# US Auto Supply — Sterling Heights Inventory Scraper

Scrapes the live vehicle inventory from the US Auto Supply junkyard at
7575 18½ Mile Rd, Sterling Heights, MI 48314.

## How it works

The scraper **does not** load the public website. Instead it fetches a
single CrushYMS XML inventory feed that the website itself uses as its
data source:

```
http://45.79.157.162/1066_inventory.xml
```

One HTTP request retrieves the complete inventory (~1 000+ vehicles).
The feed includes fields not visible on the public site, notably the
full VIN for most vehicles.

All page fetches are routed through the `webcache` service (checked
before every request, stored on miss).

On cache misses, outbound requests to the inventory host are gated by the
Request Authorization service via gRPC permits.

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run once
python scraper.py
```

The first run creates `inventory.db` (SQLite) in the same directory.

## Scheduled use (cron)

```cron
# Run daily at 07:00 local time
0 7 * * * cd /path/to/us_auto_parts_sterling_heights && python scraper.py >> scraper.log 2>&1
```

`robots.txt` specifies a 10-second crawl delay.  Because this scraper
makes only a single request per run the delay is irrelevant in practice.

## Rate-limit / 429 behaviour

This scraper does not implement local 429 backoff.  Rate limiting is
handled centrally by the request-authorization/cache stack so backoff is
applied consistently across all scraper workers in the cluster.

## Output

All data is written to `inventory.db`.  See [schema.md](schema.md) for
the full table and column documentation.

Each run appends one row to `scrape_runs` and upserts all vehicles from
the feed into `vehicles`.  Vehicles no longer present in the feed have
their `is_active` flag set to `False`.

## robots.txt summary

| Directive | Value |
|-----------|-------|
| Disallow  | `/wp-admin/` only |
| Allow     | `/wp-admin/admin-ajax.php` |
| Crawl-delay | 10 s |

The inventory feed URL (`http://45.79.157.162/…`) is a separate host
and is not governed by the `robots.txt` at `usautosupplymi.com`.
