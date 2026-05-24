import sys
import time

from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from updater import RecentPartsDirectUpdater
from utils.Exceptions import Browser403Error, InternetDownError, NoProgressException, TreeBuilderError


if __name__ == "__main__":
    args = sys.argv
    if len(args) not in [3, 4, 5, 6]:
        print(
            "Expected arguments: python3 run.py config instance_name [years_to_refresh] "
            "[max_cache_age_days] [cache_version], exiting"
        )
        sys.exit(1)

    config_name = args[1]
    instance_name = args[2]
    years_to_refresh = int(args[3]) if len(args) >= 4 else 7
    max_cache_age_days = int(args[4]) if len(args) >= 5 else 30
    cache_version = int(args[5]) if len(args) >= 6 else 1

    updater = RecentPartsDirectUpdater(
        config_name,
        instance_name,
        years_to_refresh=years_to_refresh,
        max_cache_age_days=max_cache_age_days,
        cache_version=cache_version,
    )

    while True:
        try:
            updater.scrape()
            break
        except NoProgressException as ex:
            print("Stopped making progress, stopping process")
            raise ex
        except Browser403Error:
            print("403 error caught, exiting")
            sys.exit(0)
        except TreeBuilderError:
            print("Tree builder error caught, exiting now")
            sys.exit(0)
        except InternetDownError:
            print("Internet down, pause for 60 seconds and restart")
            time.sleep(60)
        except Exception as ex:
            print(ex)
            time.sleep(60)
