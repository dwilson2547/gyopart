import sys
import time
from partsdirectscraperV2 import PartsDirectScraper
from utils.Exceptions import NoProgressException, TreeBuilderError, PageRetrievalError, Browser403Error, InternetDownError

if __name__ == '__main__':
    args = sys.argv
    if len(args) != 3:
        print('Expected two arguments (python3 run.py config instance_name), exiting')
        sys.exit(1)

    config_name = args[1]
    instance_name = args[2]

    pds = PartsDirectScraper(config_name, instance_name)

    while True:
        try:
            pds.scrape()
            break
        except NoProgressException as ex:
            print('Stopped making progress, stopping process')
            raise ex
        except Browser403Error as ex:
            print('403 error caught, exiting')
            sys.exit(0)
        except TreeBuilderError as ex:
            print('Tree builder error caught, exiting now')
            sys.exit(0)
        except InternetDownError as ex:
            print('Internet down, pause for 60 seconds and restart')
            time.sleep(60)
        except Exception as ex:
            print(ex)
            time.sleep(60)