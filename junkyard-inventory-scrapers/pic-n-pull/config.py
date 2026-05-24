import os
from pathlib import Path


class Config:
    # ── Scraper identity ──────────────────────────────────────────────────────
    SOURCE: str = "pic_n_pull"
    CLIENT_NAME: str = "pic_n_pull_inventory"
    CHAIN: str = "Pick-n-Pull"

    # ── API endpoints ──────────────────────────────────────────────────────────
    BASE_URL: str = "https://www.picknpull.com"
    LOCATIONS_URL: str = f"{BASE_URL}/api/locations/inventory"
    VEHICLE_SEARCH_URL: str = f"{BASE_URL}/api/vehicle/search"
    SEARCH_DISTANCE_MILES: int = 1

    # ── Shared service clients ─────────────────────────────────────────────────
    WEBCACHE_URL: str = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", "3600"))

    # ── HTTP headers ───────────────────────────────────────────────────────────
    HEADERS: dict = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.picknpull.com/check-inventory/vehicle-search",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
