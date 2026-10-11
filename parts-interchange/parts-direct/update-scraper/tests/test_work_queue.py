"""Needs a throwaway Postgres: UPDATER_TEST_DATABASE_URL (schema is created from the 0.3.0 models)."""
import os
import sys
from datetime import datetime, timedelta

import psycopg2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import work_queue as q  # noqa: E402

URL = os.environ.get("UPDATER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="UPDATER_TEST_DATABASE_URL not set")


@pytest.fixture
def cur():
    from sqlalchemy import create_engine
    from parts_interchange_common.models import Base
    eng = create_engine(URL.replace("postgresql://", "postgresql+psycopg2://"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    eng.dispose()
    conn = psycopg2.connect(URL)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("INSERT INTO manufacturer (id, name) VALUES (1, 'Fiat'), (2, 'Toyota')")
    yield c
    conn.close()


def add(cur, model, status, mfr=1, last=None, nxt=None, url="https://x/v"):
    cur.execute(
        "INSERT INTO scrape_target (manufacturer_id, year, make, model, trim, engine, page_url, status, "
        "last_scraped_at, next_attempt_at, attempts, created_at) VALUES (%s,'2015','jeep',%s,'base','v6',%s,%s,%s,%s,0,now()) RETURNING id",
        (mfr, model, url, status, last, nxt),
    )
    return cur.fetchone()[0]


def test_claim_order_pending_then_failed_then_stale(cur):
    now = datetime.utcnow()
    add(cur, "fresh", "done", last=now - timedelta(days=10))
    stale = add(cur, "stale", "done", last=now - timedelta(days=200))
    failed = add(cur, "failed", "failed")
    pending = add(cur, "pending", "pending")
    add(cur, "other-mfr", "pending", mfr=2)
    order = [q.claim_next(cur, 1, 180).id for _ in range(3)]
    assert order == [pending, failed, stale]
    assert q.claim_next(cur, 1, 180) is None  # fresh one isn't due; leased ones are skipped


def test_lease_hides_a_claimed_vehicle_and_release_returns_it(cur):
    t = add(cur, "a", "pending")
    assert q.claim_next(cur, 1, 180).id == t
    assert q.claim_next(cur, 1, 180) is None
    q.release(cur, t)
    assert q.claim_next(cur, 1, 180).id == t


def test_failed_backs_off_and_counts_attempts(cur):
    t = add(cur, "a", "pending")
    q.claim_next(cur, 1, 180)
    q.mark_failed(cur, t, "boom")
    cur.execute("SELECT status, attempts, next_attempt_at > now() AT TIME ZONE 'utc' FROM scrape_target WHERE id=%s", (t,))
    assert cur.fetchone() == ("failed", 1, True)
    assert q.claim_next(cur, 1, 180) is None


def test_no_catalog_is_rechecked_only_after_refresh(cur):
    t = add(cur, "a", "pending")
    q.claim_next(cur, 1, 180)
    q.mark_no_catalog(cur, t)
    assert q.claim_next(cur, 1, 180) is None
    cur.execute("UPDATE scrape_target SET last_scraped_at = now() - interval '181 days' WHERE id=%s", (t,))
    assert q.claim_next(cur, 1, 180).id == t


def test_discovery_inserts_once_and_refreshes_url(cur):
    assert q.upsert_discovered(cur, 1, "2025", "jeep", "wrangler", "x", "y", "https://a") is True
    assert q.upsert_discovered(cur, 1, "2025", "jeep", "wrangler", "x", "y", "https://b") is False
    cur.execute("SELECT count(*), max(page_url) FROM scrape_target")
    assert cur.fetchone() == (1, "https://b")
