"""Exit-code and result contract between a scraper and scrape-job-manager.

The operator (web-scrapers/scrape-job-manager, design §5.5) decides retry vs. suspend from the
process exit code, and reads a JSON result from the pod's termination message:

    0   completed — result payload written
    75  transient (network, 5xx, rate-limit service or DB unreachable) — operator retries with backoff
    65  broken (selector drift, empty feed, blocked/429, bad data) — no retry; counts toward suspension
    1   anything unclassified — operator retries once

Usage in a scraper:

    from scrape_contract import Broken, run

    def main() -> dict:
        ...
        return {"items": total_in_feed, "new": n, "updated": u, "removed": r}

    if __name__ == "__main__":
        run(main)

Raise `Broken("why")` for failures a retry cannot fix. Everything else is classified by type.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Callable

EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_DATAERR = 65
EXIT_TEMPFAIL = 75

TERMINATION_LOG = os.environ.get("SCRAPE_TERMINATION_LOG", "/dev/termination-log")

log = logging.getLogger("scrape_contract")


class Broken(Exception):
    """The scraper cannot succeed until someone fixes it (or the site): do not retry."""


class Transient(Exception):
    """A retry later may succeed."""


def _http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def classify(exc: BaseException) -> int:
    """Map an exception to the exit code the operator acts on."""
    if isinstance(exc, Broken):
        return EXIT_DATAERR
    if isinstance(exc, Transient):
        return EXIT_TEMPFAIL

    # Imports are optional: each scraper image only carries the libraries it uses.
    try:
        import requests

        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return EXIT_TEMPFAIL
        if isinstance(exc, requests.HTTPError):
            status = _http_status(exc) or 0
            if status == 429 or status in (401, 403):
                return EXIT_DATAERR  # blocked: retrying in minutes makes it worse
            return EXIT_TEMPFAIL if status >= 500 else EXIT_DATAERR
    except ImportError:
        pass
    try:
        import httpx

        if isinstance(exc, httpx.TransportError):
            return EXIT_TEMPFAIL  # webcache unreachable
        if isinstance(exc, httpx.HTTPStatusError):
            return EXIT_TEMPFAIL if exc.response.status_code >= 500 else EXIT_DATAERR
    except ImportError:
        pass
    try:
        import grpc

        if isinstance(exc, grpc.RpcError):
            return EXIT_TEMPFAIL  # request-auth server unreachable / unavailable
    except ImportError:
        pass
    try:
        from sqlalchemy.exc import DBAPIError, OperationalError

        if isinstance(exc, OperationalError):
            return EXIT_TEMPFAIL  # DB down or connection dropped
        if isinstance(exc, DBAPIError):
            return EXIT_DATAERR  # constraint / data errors repeat on retry
    except ImportError:
        pass
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        if isinstance(exc, PlaywrightTimeout):
            return EXIT_TEMPFAIL
    except ImportError:
        pass

    if isinstance(exc, (ValueError, KeyError, IndexError, TypeError, AttributeError)):
        return EXIT_DATAERR  # parse failures: the page/feed shape changed
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return EXIT_TEMPFAIL
    return EXIT_UNKNOWN


def write_result(result: dict) -> None:
    """Write the result payload where Kubernetes surfaces it. No-op outside a pod."""
    payload = json.dumps(result, sort_keys=True, default=str)
    if len(payload) > 4000:  # termination message limit is 4 KiB
        payload = json.dumps({k: result[k] for k in ("items", "new", "updated", "removed") if k in result})
    try:
        with open(TERMINATION_LOG, "w") as fh:
            fh.write(payload)
    except OSError:
        pass
    log.info("result: %s", payload)


def run(main: Callable[[], dict | None]) -> None:
    """Run `main`, write its result, and exit with the contract's code."""
    try:
        result = main() or {}
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — every failure must map to an exit code
        code = classify(exc)
        log.error("scraper failed (exit %d): %s: %s", code, type(exc).__name__, exc)
        write_result({"error": f"{type(exc).__name__}: {exc}"[:500], "exitCode": code})
        sys.exit(code)
    write_result(result)
    sys.exit(EXIT_OK)
