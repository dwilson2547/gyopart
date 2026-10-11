"""scrape_target as a work queue (design-v2 §3.3).

Claim order for one manufacturer:
  1. pending (never scraped, or reset after an outage)
  2. failed whose backoff has passed
  3. done / no_catalog last scraped more than `refresh_after_days` ago (NULL = unknown = oldest);
     refresh_after_days=None turns refresh off (user 2026-10-11: off for every site but Mopar for now —
     the catalogues rarely change, so only new vehicles are worth the traffic)
A claim leases the row (next_attempt_at = now + LEASE) under FOR UPDATE SKIP LOCKED, so concurrent runs
for the same manufacturer never take the same vehicle, and no transaction stays open during a crawl.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from writer import Target

LEASE = timedelta(hours=12)  # longer than the slowest vehicle crawl
FAILED_BACKOFF = [timedelta(hours=6), timedelta(days=1), timedelta(days=3), timedelta(days=7)]


def manufacturer_id(cur, config_name: str) -> int:
    cur.execute("SELECT id FROM manufacturer WHERE lower(name) = %s", (config_name.lower(),))
    row = cur.fetchone()
    if not row:
        raise LookupError(f"no manufacturer named {config_name!r}")
    return row[0]


def claim_next(cur, mfr_id: int, refresh_after_days: Optional[int], lease: timedelta = LEASE) -> Optional[Target]:
    """Lease the next due vehicle and return it. The caller commits right away; the crawl runs outside
    any transaction, and the lease (next_attempt_at) keeps other runs off it until it expires — so a run
    that dies mid-vehicle just lets the lease lapse."""
    cur.execute(
        """
        UPDATE scrape_target SET next_attempt_at = (now() AT TIME ZONE 'utc') + %(lease)s
        WHERE id = (
            SELECT id FROM scrape_target
            WHERE manufacturer_id = %(m)s
              AND page_url IS NOT NULL
              AND (next_attempt_at IS NULL OR next_attempt_at <= now() AT TIME ZONE 'utc')
              AND (
                    status IN ('pending', 'failed')
                 OR (%(refresh)s AND status IN ('done', 'no_catalog')
                     AND (last_scraped_at IS NULL
                          OR last_scraped_at < (now() AT TIME ZONE 'utc') - make_interval(days => %(r)s)))
              )
            ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'failed' THEN 1 ELSE 2 END,
                     last_scraped_at NULLS FIRST, year DESC, id
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, manufacturer_id, year, make, model, trim, engine, page_url
        """,
        {"m": mfr_id, "r": refresh_after_days or 0, "refresh": refresh_after_days is not None, "lease": lease},
    )
    row = cur.fetchone()
    return Target(*row) if row else None


def release(cur, target_id: int) -> None:
    """Give a leased vehicle back untouched (run stopping on an outage before scraping it)."""
    cur.execute("UPDATE scrape_target SET next_attempt_at = NULL WHERE id = %s", (target_id,))


def queue_counts(cur, mfr_id: int, refresh_after_days: Optional[int]) -> dict:
    cur.execute(
        """
        SELECT status,
               -- due = claimable now: not leased by another run (next_attempt_at), and per claim_next's rules
               count(*) FILTER (WHERE page_url IS NOT NULL
                                AND (next_attempt_at IS NULL OR next_attempt_at <= now() AT TIME ZONE 'utc')
                                AND (status IN ('pending', 'failed')
                                     OR (%s AND status IN ('done','no_catalog') AND (last_scraped_at IS NULL
                                         OR last_scraped_at < (now() AT TIME ZONE 'utc') - make_interval(days => %s))))) AS due,
               count(*)
        FROM scrape_target WHERE manufacturer_id = %s GROUP BY status
        """,
        (refresh_after_days is not None, refresh_after_days or 0, mfr_id),
    )
    return {status: {"due": due, "total": total} for status, due, total in cur.fetchall()}


def anything_due(counts: dict) -> bool:
    return any(c["due"] for c in counts.values())


def mark_no_catalog(cur, target_id: int) -> None:
    """A real page with no categories: nothing to sell for this vehicle. Re-checked on refresh."""
    cur.execute(
        "UPDATE scrape_target SET status = 'no_catalog', last_scraped_at = now() AT TIME ZONE 'utc', "
        "attempts = 0, last_error = NULL, next_attempt_at = NULL WHERE id = %s",
        (target_id,),
    )


def mark_failed(cur, target_id: int, error: str) -> None:
    cur.execute("SELECT attempts FROM scrape_target WHERE id = %s", (target_id,))
    attempts = (cur.fetchone() or [0])[0] + 1
    backoff = FAILED_BACKOFF[min(attempts, len(FAILED_BACKOFF)) - 1]
    cur.execute(
        "UPDATE scrape_target SET status = 'failed', attempts = %s, last_error = %s, "
        "next_attempt_at = (now() AT TIME ZONE 'utc') + %s WHERE id = %s",
        (attempts, error[:1000], backoff, target_id),
    )


def upsert_discovered(cur, mfr_id: int, year: str, make: str, model: str, trim: Optional[str],
                      engine: Optional[str], page_url: str) -> bool:
    """Queue a vehicle found by discovery. True if new. Known vehicles only get their URL refreshed."""
    cur.execute(
        """
        INSERT INTO scrape_target (manufacturer_id, year, make, model, trim, engine, page_url, status,
                                   attempts, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', 0, now() AT TIME ZONE 'utc')
        ON CONFLICT ON CONSTRAINT uq_scrape_target_vehicle DO UPDATE SET page_url = EXCLUDED.page_url
        RETURNING (xmax = 0)
        """,
        (mfr_id, year, make, model, trim, engine, page_url),
    )
    return cur.fetchone()[0]
