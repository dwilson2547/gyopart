"""All site traffic goes through the cluster VPN proxy (design-v2 §3.8); refuse to scrape otherwise.

The proxy is Privoxy in front of an OpenVPN tunnel. Observed 2026-10-11: with the tunnel down it fails
closed (its DNS servers are NordVPN's, unreachable without the tunnel, so requests return 500) — one
failure mode, not a guarantee. NordVPN's old check endpoint (/vpn/check/full) now only answers
{"status": "deprecated"}, so the positive check is: the exit IP seen through the proxy must be a real
IP and differ from the direct (home) IP. Run at the start of a run and every CHECK_EVERY vehicles.
"""
from __future__ import annotations

import ipaddress
import os
import time

import requests

IP_URL = "https://api.ipify.org"
CHECK_EVERY = 50
# The VPN exit rotates about every 20 minutes and the proxy is unreachable for 30 s to 1 min while it
# does (user, 2026-10-25). Each rotation stopped the run it hit (GM, Honda, Mazda on 2026-10-24); a drop
# is waited out for up to RECOVER_WAIT_S before it counts as the VPN being down.
RECOVER_WAIT_S = 180
RECOVER_POLL_S = 15


class VpnUnavailable(Exception):
    """Transient: the run stops (exit 75) and the operator retries later."""


def proxy_url() -> str | None:
    return os.environ.get("VPN_PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def _ip(session: requests.Session, proxies: dict | None, timeout: float) -> str:
    resp = session.get(IP_URL, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    return str(ipaddress.ip_address(resp.text.strip()))


def check(timeout: float = 20.0) -> str:
    """Return the VPN exit IP; raise VpnUnavailable unless traffic demonstrably leaves through it."""
    proxy = proxy_url()
    if not proxy:
        raise VpnUnavailable("no VPN proxy configured (VPN_PROXY_URL / HTTPS_PROXY)")
    with requests.Session() as s:
        s.trust_env = False  # the direct probe must not pick up HTTPS_PROXY
        try:
            exit_ip = _ip(s, {"http": proxy, "https": proxy}, timeout)
        except (requests.RequestException, ValueError) as exc:
            raise VpnUnavailable(f"no exit IP through {proxy}: {exc}") from exc
        try:
            home_ip = _ip(s, None, timeout)
        except (requests.RequestException, ValueError) as exc:
            raise VpnUnavailable(f"can't read the direct IP to compare: {exc}") from exc
    if exit_ip == home_ip:
        raise VpnUnavailable(f"traffic through the proxy leaves on the home IP {home_ip}")
    return exit_ip


def wait_until_up(max_wait_s: float = RECOVER_WAIT_S, poll_s: float = RECOVER_POLL_S) -> str:
    """check(), retried every poll_s for up to max_wait_s: rides out an exit rotation. Raises the last
    VpnUnavailable if the proxy is still down after that."""
    deadline = time.monotonic() + max_wait_s
    while True:
        try:
            return check()
        except VpnUnavailable:
            if time.monotonic() + poll_s > deadline:
                raise
            time.sleep(poll_s)
