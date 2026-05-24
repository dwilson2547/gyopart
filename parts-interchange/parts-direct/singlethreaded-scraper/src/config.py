import os


class Config:
    CLIENT_NAME: str = "parts_direct"
    IMG_BUCKET: str = "parts-direct"

    WEBCACHE_URL: str = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    IMGCACHE_URL: str = os.environ.get("IMGCACHE_URL", "http://imgcache.scrapestack.local")
    IMGCACHE_TIMEOUT: float = float(os.environ.get("IMGCACHE_TIMEOUT", "30.0"))
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", str(30 * 24 * 3600)))

    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )

    PARTS_DATABASE_URL: str = os.environ.get(
        "PARTS_DATABASE_URL",
        "postgresql://scrapestack:6pf6pZ6tI_-T01PBRZHbHg@localhost:5433/parts_interchange",
    )

    REMOTE_EXECUTOR: str = os.environ.get("remote_executor", "http://localhost:4444/wd/hub")
    CHROME_PROXY: str = os.environ.get("chrome_proxy", "http://192.168.0.240:8118")
    PAGE_REQUEST_DELAY: float = float(os.environ.get("PAGE_REQUEST_DELAY", "3.5"))
