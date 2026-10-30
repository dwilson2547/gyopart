import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("WEBCACHE_URL", "http://unused")
os.environ.setdefault("IMGCACHE_URL", "http://unused")
os.environ.setdefault("REQUEST_AUTH_URL", "unused:9000")
from scraper_v2 import UpdaterV2, image_origin_url  # noqa: E402

PRODUCT = "https://cdn-product-images.revolutionparts.io/assets/0f0d3bebb3c2e4514ca0951f76013cab.webp"
ILLUSTRATION = "https://cdn-illustrations.revolutionparts.io/strapr1/35bc3d37cc84d9bccf938209162d96e9/11b4dc893f85e95944f63e3dfb4cf4ba.png"


def test_origin_urls():
    assert image_origin_url(PRODUCT) == \
        "https://s3.amazonaws.com/rp-part-images/assets/0f0d3bebb3c2e4514ca0951f76013cab.webp"
    assert image_origin_url(ILLUSTRATION) == \
        "https://dz310nzuyimx0.cloudfront.net/strapr1/35bc3d37cc84d9bccf938209162d96e9/11b4dc893f85e95944f63e3dfb4cf4ba.png"
    assert image_origin_url("https://cdn.revolutionparts.io/x/logo.png") is None


def _scraper(responses):
    fetched = []

    def get(url, proxies):
        fetched.append(url)
        status, body = responses[len(fetched) - 1]
        return SimpleNamespace(ok=status == 200, status_code=status, content=body,
                               raise_for_status=lambda: None if status == 200 else (_ for _ in ()).throw(
                                   RuntimeError(f"HTTP {status}")))
    s = SimpleNamespace(_get_image=get)
    return s, fetched


def test_origin_first_and_no_cdn_request_when_it_has_the_image():
    s, fetched = _scraper([(200, b"img")])
    assert UpdaterV2._fetch_image(s, PRODUCT, None) == b"img"
    assert fetched == [image_origin_url(PRODUCT)]


def test_falls_back_to_the_cdn_when_the_origin_lacks_it():
    s, fetched = _scraper([(404, b""), (200, b"img")])
    assert UpdaterV2._fetch_image(s, ILLUSTRATION, None) == b"img"
    assert fetched == [image_origin_url(ILLUSTRATION), ILLUSTRATION]


def test_hosts_without_an_origin_go_straight_to_their_url():
    s, fetched = _scraper([(200, b"logo")])
    url = "https://cdn.revolutionparts.io/x/logo.png"
    assert UpdaterV2._fetch_image(s, url, None) == b"logo"
    assert fetched == [url]
