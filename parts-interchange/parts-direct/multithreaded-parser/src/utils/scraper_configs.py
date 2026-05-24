import logging
import os

log = logging.getLogger()

OVERRIDE_ROOT_PATH = os.getenv("save_dir")

class ScraperConfigs:
    """
    Static class containing list of scrape jobs
    """

    ROOT_PATH = "/home/daniel/rsync-dump" if not OVERRIDE_ROOT_PATH else OVERRIDE_ROOT_PATH

    configs = {
        'ford': {
            'base_url': 'https://www.oemfordpart.com',
            'data_dir': f'{ROOT_PATH}/ford',
            'port': '9222'
        },
        'acura': {
            'base_url': 'https://www.acuraoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/acura',
            'port': '9223'
        },
        'gm': {
            'base_url': 'https://www.gmpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/gm',
            'port': '9224'
        },
        'honda': {
            'base_url': 'https://www.hondapartsdirect.com',
            'data_dir': f'{ROOT_PATH}/honda',
            'port': '9225'
        },
        'subaru': {
            'base_url': 'https://www.subarudirectwholesale.com',
            'data_dir': f'{ROOT_PATH}/subaru',
            'port': '9226'
        },
        'nissan': {
            'base_url': 'https://www.nissanwholesaledirect.com',
            'data_dir': f'{ROOT_PATH}/nissan',
            'port': '9227'
        },
        'infiniti': {
            'base_url': 'https://www.infinitiwholesaledirect.com',
            'data_dir': f'{ROOT_PATH}/infiniti',
            'port': '9228'
        },
        'toyota': {
            'base_url': 'https://wholesaledirect.moderntoyota.com',
            'data_dir': f'{ROOT_PATH}/toyota',
            'port': '9229'
        },
        'hyundai': {
            'base_url': 'https://www.hyundaioempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/hyundai',
            'port': '9230'
        },
        'vw': {
            'base_url': 'https://www.volkswagenpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/vw',
            'port': '9231'
        },
        'mopar': {
            'base_url': 'https://www.moparoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mopar',
            'port': '9232'
        },
        'mitsubishi': {
            'base_url': 'https://www.mitsubishidirectparts.com',
            'data_dir': f'{ROOT_PATH}/mitsubishi',
            'port': '9233'
        },
        'mini': {
            'base_url': 'https://www.minipartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mini',
            'port': '9234'
        },
        'porsche': {
            'base_url': 'https://www.porscheoemwarehouse.com',
            'data_dir': f'{ROOT_PATH}/porsche',
            'port': '9235'
        },
        'jaguar': {
            'base_url': 'https://www.jaguarparts.com',
            'data_dir': f'{ROOT_PATH}/jaguar',
            'port': '9236'
        },
        'audi': {
            'base_url': 'https://www.flowaudipartsdirect.com',
            'data_dir': f'{ROOT_PATH}/audi',
            'port': '9237'
        },
        'bmw': {
            'base_url': 'https://www.bmwpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/bmw',
            'port': '9238'
        },
        'mercedes': {
            'base_url': 'https://www.mbdirectparts.com',
            'data_dir': f'{ROOT_PATH}/mercedes',
            'port': '9239'
        },
        'mazda': {
            'base_url': 'https://www.mazdapartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mazda',
            'port': '9231'
        },
        'lexus': {
            'base_url': 'https://www.lexusdirectparts.com',
            'data_dir': f'{ROOT_PATH}/lexus',
            'port': '9232'
        },
        'kia': {
            'base_url': 'https://www.kiapartsonline.com',
            'data_dir': f'{ROOT_PATH}/kia',
            'port': '9233'
        },
        'suzuki': {
            'base_url': 'https://www.suzukicarparts.com',
            'data_dir': f'{ROOT_PATH}/suzuki',
            'port': '9234'
        },
        'volvo': {
            'base_url': 'https://www.volvocarsoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/volvo',
            'port': '9235'
        }
    }

    @staticmethod
    def get(name: str):
        """
        Returns config object for provided name
        """
        try:
            return ScraperConfigs.configs[name]
        except KeyError as ex:
            log.error('Key error caught while loading config, no config for provided name: %s', name)
            raise ex
