import os


class Config:
    # ── API endpoints ────────────────────────────────────────────────────────
    LOCATIONS_URL: str    = "https://enterpriseservice.pullapart.com/Location"
    LOCATIONS_PARAMS: dict = {"siteTypeID": -1}
    MAKES_URL: str        = "https://inventoryservice.pullapart.com/Make/"
    INVENTORY_URL: str    = "https://inventoryservice.pullapart.com/Vehicle/Search"
    DETAILS_URL: str      = (
        "https://inventoryservice.pullapart.com"
        "/VehicleExtendedInfo/{loc_id}/{ticket_id}/{line_id}"
    )

    # ── Shared service clients ───────────────────────────────────────────────
    SOURCE: str           = "pull_a_part"
    CHAIN: str            = "Pull-A-Part"
    CLIENT_NAME: str      = "pull_a_part_inventory"
    WEBCACHE_URL: str     = os.environ.get("WEBCACHE_URL", "http://webcache.scrapestack.local")
    WEBCACHE_TIMEOUT: float = float(os.environ.get("WEBCACHE_TIMEOUT", "30.0"))
    REQUEST_AUTH_SERVER_URL: str = os.environ.get(
        "REQUEST_AUTH_SERVER_URL", "request-auth-server.scrapestack.local:9000"
    )
    CACHE_MAX_AGE_SECONDS: int = int(os.environ.get("CACHE_MAX_AGE_SECONDS", "3600"))

    HEADERS: dict = {
        "Accept":       "application/json",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
