"""Entry point for update scraper v2, speaking scrape-job-manager's contract.

  python run_v2.py --config fiat [--max-vehicles N] [--max-minutes M] [--refresh-after-days 180]
                   [--discovery auto|force|skip] [--discovery-interval-days 90] [--no-refresh]

Exit codes: 0 stopped normally (deadline / queue empty / limit) · 75 transient (site unavailable, VPN
down) · 65 blocked or repeatedly failing · 1 unexpected. The result payload goes to the pod's
termination message.

Environment:
  PARTS_INTERCHANGE_DATABASE_URL   catalogue DB (owner role)
  WEBCACHE_URL, IMGCACHE_URL, REQUEST_AUTH_URL   scrape-stack services
  VPN_PROXY_URL (or HTTPS_PROXY)   the cluster VPN proxy; NO_PROXY must cover in-cluster hosts
  SCRAPE_DEADLINE                  RFC 3339; injected by scrape-job-manager (design-v2 §3.3)
  SCRAPE_PARAMS                    JSON from the ScrapeJob, e.g. {"config": "fiat"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

TERMINATION_LOG = os.environ.get("SCRAPE_TERMINATION_LOG", "/dev/termination-log")


def write_result(result: dict) -> None:
    payload = json.dumps(result, default=str)[:4000]
    try:
        with open(TERMINATION_LOG, "w") as fh:
            fh.write(payload)
    except OSError:
        pass
    print("result:", payload)


def parse_deadline(args) -> datetime | None:
    deadlines = []
    if os.environ.get("SCRAPE_DEADLINE"):
        d = datetime.fromisoformat(os.environ["SCRAPE_DEADLINE"].replace("Z", "+00:00"))
        deadlines.append(d.astimezone(timezone.utc).replace(tzinfo=None))
    if args.max_minutes:
        deadlines.append(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=args.max_minutes))
    return min(deadlines) if deadlines else None


def normalise_args(argv: list[str]) -> list[str]:
    """scrape-job-manager passes each ScrapeJob param as --<key>=<value>, keys as written in the YAML
    (snake_case) and booleans as true/false; map that onto this CLI's flags."""
    out = []
    for arg in argv:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            key = key.replace("_", "-")
            if key == "refresh":
                if value.lower() in ("false", "0", "no"):
                    out.append("--no-refresh")
                continue
            arg = f"--{key}={value}"
        out.append(arg)
    return out


def main() -> int:
    params = json.loads(os.environ.get("SCRAPE_PARAMS") or "{}")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=params.get("config"))
    ap.add_argument("--max-vehicles", type=int, default=params.get("max_vehicles"))
    ap.add_argument("--max-minutes", type=float, default=params.get("max_minutes"))
    ap.add_argument("--refresh-after-days", type=int, default=int(params.get("refresh_after_days", 180)))
    ap.add_argument("--no-refresh", action="store_true", default=params.get("refresh") is False,
                    help="only new/failed vehicles; never re-scrape stale ones")
    ap.add_argument("--discovery-interval-days", type=int, default=int(params.get("discovery_interval_days", 90)))
    ap.add_argument("--discovery", choices=("auto", "force", "skip"), default=params.get("discovery", "auto"),
                    help="list the site's vehicles first: when due (90 days), always, or never")
    args = ap.parse_args(normalise_args(sys.argv[1:]))
    if not args.config:
        ap.error("--config (or SCRAPE_PARAMS config) is required")

    from scraper_v2 import RunStopped, UpdaterV2

    updater = UpdaterV2(
        args.config,
        os.environ["PARTS_INTERCHANGE_DATABASE_URL"],
        deadline=parse_deadline(args),
        refresh_after_days=None if args.no_refresh else args.refresh_after_days,
        max_vehicles=args.max_vehicles,
        discovery=args.discovery,
        discovery_interval_days=args.discovery_interval_days,
    )
    try:
        stats = updater.run()
    except RunStopped as stop:
        updater.stats.stop_reason = stop.reason
        write_result({**updater.stats.payload(), "error": stop.reason, "exitCode": stop.exit_code})
        return stop.exit_code
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        write_result({**updater.stats.payload(), "error": f"{type(ex).__name__}: {ex}"[:500], "exitCode": 1})
        return 1
    write_result(stats.payload())
    return 0


if __name__ == "__main__":
    sys.exit(main())
