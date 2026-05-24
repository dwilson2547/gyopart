from CachedParser import CachedParser, CategoryPageParser, DiagramPageParser, PartPageParser
from BucketUtils import BucketUtils

BUCKET_NAME = 'part-images'

base_url = 'https://www.gmpartsdirect.com'

bucket_utils = BucketUtils()

with open('/home/daniel/documents/selenium_test_project/parts-direct-scraper/example_htmls/part_page.html') as f:
    page_text = f.read()

part_page_parser = PartPageParser(base_url)

part_data = part_page_parser.parse(page_text)

bucket_utils.dump_json_to_bucket(BUCKET_NAME, 'test', 'parts.json', part_data)
