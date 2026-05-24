import sys
import time
from scraper import PartsDirectScraper, NoProgressException

configs = {
    'ford': {
        'base_url': 'https://www.oemfordpart.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/ford',
        'port': '9222'
    },
    'acura': {
        'base_url': 'https://www.acuraoempartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/acura',
        'port': '9223'
    },
    'gm': {
        'base_url': 'https://www.gmpartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/gm',
        'port': '9224'
    },
    'honda': {
        'base_url': 'https://www.hondapartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/honda',
        'port': '9225'
    },
    'subaru': {
        'base_url': 'https://www.subarudirectwholesale.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/subaru',
        'port': '9226'
    },
    'nissan': {
        'base_url': 'https://www.nissanwholesaledirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/nissan',
        'port': '9227'
    },
    'infiniti': {
        'base_url': 'https://www.infinitiwholesaledirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/infiniti',
        'port': '9228'
    },
    'toyota': {
        'base_url': 'https://wholesaledirect.moderntoyota.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/toyota',
        'port': '9229'
    },
    'hyundai': {
        'base_url': 'https://www.hyundaioempartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/hyundai',
        'port': '9230'
    },
    'vw': {
        'base_url': 'https://www.volkswagenpartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/vw',
        'port': '9231'
    },
    'mopar': {
        'base_url': 'https://www.moparoempartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/mopar',
        'port': '9232'
    },
    'mitsubishi': {
        'base_url': 'https://www.mitsubishidirectparts.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/mitsubishi',
        'port': '9233'
    },
    'mini': {
        'base_url': 'https://www.minipartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/mini',
        'port': '9234'
    },
    'porsche': {
        'base_url': 'https://www.porschepartsnow.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/porsche',
        'port': '9235'
    },
    'jaguar': {
        'base_url': 'https://www.jaguarparts.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/jaguar',
        'port': '9236'
    },
    'audi': {
        'base_url': 'https://www.flowaudipartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/audi',
        'port': '9237'
    },
    'bmw': {
        'base_url': 'https://www.bmwpartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/bmw',
        'port': '9238'
    },
    'mercedes': {
        'base_url': 'https://www.mbdirectparts.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/mercedes',
        'port': '9239'
    },
    'mazda': {
        'base_url': 'https://www.mazdapartsdirect.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/mazda',
        'port': '9231'
    },
    'lexus': {
        'base_url': 'https://www.lexusdirectparts.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/lexus',
        'port': '9232'
    },
    'kia': {
        'base_url': 'https://www.kiapartsonline.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/kia',
        'port': '9233'
    },
    'suzuki': {
        'base_url': 'https://www.suzukicarparts.com',
        'data_dir': '/home/daniel/documents/selenium_test_project/parts-direct-data/suzuki',
        'port': '9234'
    }
}

if __name__ == '__main__':
    args = sys.argv
    if len(args) != 3:
        print('Expected two arguments (python3 run.py config instance_name), exiting')
        sys.exit(1)
    if args[1] not in configs:
        print('Unknown config: ' + args[1])
        print('Known Configs: ' + str(list(configs.keys())))

    base_url = configs[args[1]]['base_url']
    data_dir = configs[args[1]]['data_dir']
    debug_port = configs[args[1]]['port']
    instance_name = args[2]
    
    pds = PartsDirectScraper(base_url=base_url, instance_name=instance_name, data_dir=data_dir, debug_port=debug_port, config_name=args[1])

    while True:
        try:
            pds.scrape_car_list()
            break
        except NoProgressException as ex:
            print('Stopped making progress, stopping process')
            raise ex
        except Exception as ex:
            print(ex)
            time.sleep(60)
