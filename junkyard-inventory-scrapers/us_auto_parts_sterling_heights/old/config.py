
class Config:

    configs = {
        'us-auto-supply-wayne': {
            'url': 'https://usautosupplymi.com/upull/wayne/wayne-inventory/',
            'scraper': 'us-auto-supply-scraper'
        },
        'us-auto-supply-sterling-heights': {
            'url': 'https://usautosupplymi.com/upull/sterling-heights/sterling-heights-inventory/',
            'scraper': 'us-auto-supply-scraper'
        }
    }

    @staticmethod
    def get(name: str):
        return Config.configs[name]