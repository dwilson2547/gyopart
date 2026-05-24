import os

OVERRIDE_ROOT_PATH = os.getenv("save_dir")

class CarConfigs:

    ROOT_PATH = "/home/daniel/rsync-dump" if not OVERRIDE_ROOT_PATH else OVERRIDE_ROOT_PATH

    configs = {
        'ford': {
            'base_url': 'https://www.oemfordpart.com',
            'data_dir': f'{ROOT_PATH}/ford',
            'port': '9222',
            'skip': True
        },
        'acura': {
            'base_url': 'https://www.acuraoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/acura',
            'port': '9223',
            'skip': True
        },
        'gm': {
            'base_url': 'https://www.gmpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/gm',
            'port': '9224',
            'skip': True
        },
        'honda': {
            'base_url': 'https://www.hondapartsdirect.com',
            'data_dir': f'{ROOT_PATH}/honda',
            'port': '9225',
            'skip': True
        },
        'subaru': {
            'base_url': 'https://www.subarudirectwholesale.com',
            'data_dir': f'{ROOT_PATH}/subaru',
            'port': '9226',
            'skip': True
        },
        'nissan': {
            'base_url': 'https://www.nissanwholesaledirect.com',
            'data_dir': f'{ROOT_PATH}/nissan',
            'port': '9227',
            'skip': True
        },
        'infiniti': {
            'base_url': 'https://www.infinitiwholesaledirect.com',
            'data_dir': f'{ROOT_PATH}/infiniti',
            'port': '9228',
            'skip': True
        },
        'toyota': {
            'base_url': 'https://wholesaledirect.moderntoyota.com',
            'data_dir': f'{ROOT_PATH}/toyota',
            'port': '9229',
            'skip': True
        },
        'hyundai': {
            'base_url': 'https://www.hyundaioempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/hyundai',
            'port': '9230',
            'skip': True
        },
        'vw': {
            'base_url': 'https://www.volkswagenpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/vw',
            'port': '9231',
            'skip': True
        },
        'mopar': {
            'base_url': 'https://www.moparoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mopar',
            'port': '9232',
            'skip': True
        },
        'mitsubishi': {
            'base_url': 'https://www.mitsubishidirectparts.com',
            'data_dir': f'{ROOT_PATH}/mitsubishi',
            'port': '9233',
            'skip': True
        },
        'mini': {
            'base_url': 'https://www.minipartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mini',
            'port': '9234',
            'skip': True
        },
        'porsche': {
            'base_url': 'https://www.porscheoemwarehouse.com',
            'data_dir': f'{ROOT_PATH}/porsche',
            'port': '9235',
            'skip': True
        },
        'jaguar': {
            'base_url': 'https://www.jaguarparts.com',
            'data_dir': f'{ROOT_PATH}/jaguar',
            'port': '9236',
            'skip': True
        },
        'audi': {
            'base_url': 'https://www.flowaudipartsdirect.com',
            'data_dir': f'{ROOT_PATH}/audi',
            'port': '9237',
            'skip': True
        },
        'bmw': {
            'base_url': 'https://www.bmwpartsdirect.com',
            'data_dir': f'{ROOT_PATH}/bmw',
            'port': '9238',
            'skip': True
        },
        'mercedes': {
            'base_url': 'https://www.mbdirectparts.com',
            'data_dir': f'{ROOT_PATH}/mercedes',
            'port': '9239',
            'skip': True
        },
        'mazda': {
            'base_url': 'https://www.mazdapartsdirect.com',
            'data_dir': f'{ROOT_PATH}/mazda',
            'port': '9231',
            'skip': True
        },
        'lexus': {
            'base_url': 'https://www.lexusdirectparts.com',
            'data_dir': f'{ROOT_PATH}/lexus',
            'port': '9232',
            'skip': True
        },
        'kia': {
            'base_url': 'https://www.kiapartsonline.com',
            'data_dir': f'{ROOT_PATH}/kia',
            'port': '9233'
        },
        'suzuki': {
            'base_url': 'https://www.suzukicarparts.com',
            'data_dir': f'{ROOT_PATH}/suzuki',
            'port': '9234',
            'skip': True
        },
        'volvo': {
            'base_url': 'https://www.volvocarsoempartsdirect.com',
            'data_dir': f'{ROOT_PATH}/volvo',
            'port': '9235',
            'skip': True
        }
    }

    def get(name: str):
        return CarConfigs.configs[name]
