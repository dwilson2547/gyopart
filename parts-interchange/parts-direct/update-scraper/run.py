import sys
import time

from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from updater import RecentPartsDirectUpdater
from utils.Exceptions import Browser403Error, InternetDownError, NoProgressException, TreeBuilderError


if __name__ == "__main__":
    args = sys.argv
    if len(args) not in [2, 3, 4]:
        print(
            "Usage: python3 run.py config [years_to_refresh] [max_cache_age_days]\n"
            "  config             — make config name (e.g. lexus, mopar)\n"
            "  years_to_refresh   — how many recent model years to check (default 7)\n"
            "  max_cache_age_days — max age of cached pages before re-rendering (default 30)\n"
            "\n"
            "Required env vars: WEBCACHE_URL, IMGCACHE_URL, REQUEST_AUTH_URL"
        )
        sys.exit(1)

    config_name = args[1]
    years_to_refresh = int(args[2]) if len(args) >= 3 else 7
    max_cache_age_days = int(args[3]) if len(args) >= 4 else 30

    updater = RecentPartsDirectUpdater(
        config_name,
        years_to_refresh=years_to_refresh,
        max_cache_age_days=max_cache_age_days,
    )

    while True:
        try:
            updater.scrape()
            break
        except NoProgressException as ex:
            print("Stopped making progress, stopping")
            raise ex
        except Browser403Error:
            print("403 error caught, exiting")
            sys.exit(0)
        except TreeBuilderError:
            print("Tree builder error caught, exiting")
            sys.exit(0)
        except InternetDownError:
            print("Internet down, pause for 60 seconds and restart")
            time.sleep(60)
        except Exception as ex:
            print(ex)
            time.sleep(60)
