
BUCKET_NAME = 'part-images'
INFLUX_MEASURE = 'scraper_status'

class PageType:
    CATEGORIES = 'CATEGORIES'
    DIAGRAMS = 'DIAGRAMS'
    PART = 'PART'

class Steps:
    MAKE = 'make'
    MODEL = 'model'
    TRIM = 'trim'
    ENGINE = 'engine'

class keys:
    MAKES = 'makes'
    MODELS = 'models'
    TRIMS = 'trims'
    ENGINES = 'engines'
    CATEGORIES = 'categories'
    PARTS = 'parts'
    PAGE_URL = 'page_url'
    DIAGRAMS = 'diagrams'
    CATEGORY_LINKS = 'cat_links'
    PART_NUMBER = 'part_number'

class SaveFiles:
    PARTS_FILE = 'parts.json'
    IMAGES_FILE = 'imgs.json'
    IMAGES_DIR = 'images'
    TREE_FILE = 'tree.json'
    WEBCACHE_FILE = 'webcache.json'
    WEBCACHE_DIR = 'webcache'
    CHECKSUM_FILE = 'checksums.json'
    BLANK_TREE_FILE = 'blank_tree.json'
    BACKUPS_DIR = 'save_file_backups'