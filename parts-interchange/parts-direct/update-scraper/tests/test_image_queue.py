import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("WEBCACHE_URL", "http://unused")
os.environ.setdefault("IMGCACHE_URL", "http://unused")
os.environ.setdefault("REQUEST_AUTH_URL", "unused:9000")
from scraper_v2 import ImageQueue  # noqa: E402


class FakeConn:
    def __init__(self):
        self.updates = []

    def cursor(self):
        conn = self

        class C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params):
                conn.updates.append(sorted(params[1]))
        return C()

    def commit(self):
        pass


def test_late_finishers_are_flipped_once_and_failures_never():
    gate = threading.Event()
    def download(url, name):
        if name == "slow":
            gate.wait(5)
        return name != "broken"

    q = ImageQueue(download, 4)
    for n in ("fast", "slow", "broken", "fast"):  # duplicate submit is ignored
        q.submit(n, "https://cdn/" + n)
    import time
    time.sleep(0.2)
    assert q.status("fast") is True
    assert q.status("slow") is False      # still running → remembered as written-unsaved
    assert q.status("broken") is False    # finished, failed → not remembered
    conn = FakeConn()
    assert q.flush_updates(conn, 1) == 0  # nothing finished late yet
    gate.set()
    q.drain(conn, 1, None)
    assert conn.updates == [["slow"]]     # flipped to saved after the fact, exactly once
    q.close(cancel=False)
    assert (q.saved, q.failed) == (2, 1)
