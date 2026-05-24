import os

OVERRIDE_ROOT_PATH = os.getenv('save_dir')


class CarConfigs:

    ROOT_PATH = '/mnt/z/parts_direct_recovery' if not OVERRIDE_ROOT_PATH else OVERRIDE_ROOT_PATH

    configs = {
        'ford':       {'base_url': 'https://www.oemfordpart.com',               'data_dir': f'{ROOT_PATH}/ford',       'skip': True},
        'acura':      {'base_url': 'https://www.acuraoempartsdirect.com',        'data_dir': f'{ROOT_PATH}/acura',      'skip': True},
        'gm':         {'base_url': 'https://www.gmpartsdirect.com',              'data_dir': f'{ROOT_PATH}/gm',         'skip': True},
        'honda':      {'base_url': 'https://www.hondapartsdirect.com',           'data_dir': f'{ROOT_PATH}/honda',      'skip': True},
        'subaru':     {'base_url': 'https://www.subarudirectwholesale.com',      'data_dir': f'{ROOT_PATH}/subaru',     'skip': True},
        'nissan':     {'base_url': 'https://www.nissanwholesaledirect.com',      'data_dir': f'{ROOT_PATH}/nissan',     'skip': True},
        'infiniti':   {'base_url': 'https://www.infinitiwholesaledirect.com',    'data_dir': f'{ROOT_PATH}/infiniti',   'skip': True},
        'toyota':     {'base_url': 'https://wholesaledirect.moderntoyota.com',   'data_dir': f'{ROOT_PATH}/toyota',     'skip': True},
        'hyundai':    {'base_url': 'https://www.hyundaioempartsdirect.com',      'data_dir': f'{ROOT_PATH}/hyundai',    'skip': True},
        'vw':         {'base_url': 'https://www.volkswagenpartsdirect.com',      'data_dir': f'{ROOT_PATH}/vw',         'skip': True},
        'mopar':      {'base_url': 'https://www.moparoempartsdirect.com',        'data_dir': f'{ROOT_PATH}/mopar',      'skip': True},
        'mitsubishi': {'base_url': 'https://www.mitsubishidirectparts.com',      'data_dir': f'{ROOT_PATH}/mitsubishi', 'skip': True},
        'mini':       {'base_url': 'https://www.minipartsdirect.com',            'data_dir': f'{ROOT_PATH}/mini',       'skip': True},
        'porsche':    {'base_url': 'https://www.porscheoemwarehouse.com',        'data_dir': f'{ROOT_PATH}/porsche',    'skip': True},
        'jaguar':     {'base_url': 'https://www.jaguarparts.com',                'data_dir': f'{ROOT_PATH}/jaguar',     'skip': True},
        'audi':       {'base_url': 'https://www.flowaudipartsdirect.com',        'data_dir': f'{ROOT_PATH}/audi',       'skip': True},
        'bmw':        {'base_url': 'https://www.bmwpartsdirect.com',             'data_dir': f'{ROOT_PATH}/bmw',        'skip': True},
        'mercedes':   {'base_url': 'https://www.mbdirectparts.com',              'data_dir': f'{ROOT_PATH}/mercedes',   'skip': True},
        'mazda':      {'base_url': 'https://www.mazdapartsdirect.com',           'data_dir': f'{ROOT_PATH}/mazda',      'skip': True},
        'lexus':      {'base_url': 'https://www.lexusdirectparts.com',           'data_dir': f'{ROOT_PATH}/lexus',      'skip': True},
        'kia':        {'base_url': 'https://www.kiapartsonline.com',             'data_dir': f'{ROOT_PATH}/kia'},
        'suzuki':     {'base_url': 'https://www.suzukicarparts.com',             'data_dir': f'{ROOT_PATH}/suzuki',     'skip': True},
        'volvo':      {'base_url': 'https://www.volvocarsoempartsdirect.com',    'data_dir': f'{ROOT_PATH}/volvo',      'skip': True},
    }
