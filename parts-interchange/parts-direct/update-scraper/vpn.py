"""All site traffic goes through the cluster VPN proxy (design-v2 §3.8); refuse to scrape otherwise.

The proxy is Privoxy in front of an OpenVPN tunnel. Observed 2026-10-11 with the tunnel down: it fails
closed (its DNS servers are NordVPN's, unreachable without the tunnel, so every request returns 500),
but that is one failure mode, not a guarantee — hence a positive check that NordVPN reports the
connection as protected, at the start of a run and every CHECK_EVERY vehicles.
"""
from __future__ import annotations

import os

import requests

CHECK_URL = "https://api.nordvpn.com/vpn/check/full"
CHECK_EVERY = 50


class VpnUnavailable(Exception):
    """Transient: the run stops (exit 75) and the operator retries later."""


def proxy_url() -> str | None:
    return os.environ.get("VPN_PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def check(timeout: float = 20.0) -> str:
    """Return the exit IP if NordVPN says the connection is protected; raise VpnUnavailable otherwise."""
    proxy = proxy_url()
    if not proxy:
        raise VpnUnavailable("no VPN proxy configured (VPN_PROXY_URL / HTTPS_PROXY)")
    try:
        resp = requests.get(CHECK_URL, proxies={"http": proxy, "https": proxy}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise VpnUnavailable(f"VPN check failed through {proxy}: {exc}") from exc
    if str(data.get("status", "")).lower() != "protected":
        raise VpnUnavailable(f"VPN check says {data.get('status')!r} (ip {data.get('ip')})")
    return str(data.get("ip", "?"))
