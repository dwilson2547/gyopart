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
                conn.updates.append(sorted(zip(params[0], params[1])))
        return C()

    def commit(self):
        pass


def test_late_finishers_are_flipped_once_and_failures_never():
    gate = threading.Event()
    def download(url, name):
        if name == "slow":
            gate.wait(5)
            return "h-slow"           # stored now: its hash
        if name == "fast":
            return True               # already in the bucket: no hash
        return False

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
    assert conn.updates == [[("slow", "h-slow")]]  # flipped to saved/uploaded with its hash, exactly once
    assert q.content_hash("slow") == "h-slow" and q.content_hash("fast") is None
    q.close(cancel=False)
    assert (q.saved, q.failed) == (2, 1)


class FakeBucket:
    def __init__(self, existing=None):
        self.objects = {}
        self.meta = dict(existing or {})          # key -> metadata dict as stat_object reports it

    def stat_object(self, bucket, key):
        from minio.error import S3Error
        if key not in self.meta:
            raise S3Error(response=None, code="NoSuchKey", message="missing", resource=key, request_id="r", host_id="h")

        class St:
            metadata = self.meta[key]
        return St()

    def put_object(self, bucket, key, data, length, content_type=None, metadata=None):
        self.objects[key] = data.read()
        self.meta[key] = {f"X-Amz-Meta-{k.capitalize()}": v for k, v in (metadata or {}).items()}


def _scraper(bucket):
    from scraper_v2 import UpdaterV2 as Scraper
    s = Scraper.__new__(Scraper)       # no browser, DB or services: only what save_image touches
    s.config_name, s.bucket, s.bucket_name = "acura", bucket, "part-images"
    s._fetch_image = lambda url, proxies: b"png-bytes"
    return s


def test_save_image_stores_at_bucket_path_and_returns_hash(monkeypatch):
    import blake3
    import scraper_v2
    monkeypatch.setattr(scraper_v2.vpn, "proxy_url", lambda: None)
    b = FakeBucket()
    assert _scraper(b).save_image("https://cdn/x.png", "x.png") == blake3.blake3(b"png-bytes").hexdigest()
    assert b.objects["acura/images/x.png"] == b"png-bytes"
    assert b.meta["acura/images/x.png"] == {"X-Amz-Meta-Blake3": blake3.blake3(b"png-bytes").hexdigest()}


def test_save_image_skips_objects_already_stored(monkeypatch):
    import scraper_v2
    monkeypatch.setattr(scraper_v2.vpn, "proxy_url", lambda: None)
    s = _scraper(FakeBucket(existing={"acura/images/x.png": {}, "acura/images/y.png": {"X-Amz-Meta-Blake3": "h1"}}))
    s._fetch_image = lambda url, proxies: (_ for _ in ()).throw(AssertionError("downloaded"))
    assert s.save_image("https://cdn/x.png", "x.png") is True      # old upload: no hash on the object
    assert s.save_image("https://cdn/y.png", "y.png") == "h1"      # earlier run's upload: hash read back
