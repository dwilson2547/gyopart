from CachedParser import CachedParser, CategoryPageParser, DiagramPageParser, PartPageParser
# with open('/home/daniel/documents/selenium_test_project/parts-direct-scraper/example_htmls/categories_page.html') as f:
#     page_text = f.read()

base_url = 'https://www.gmpartsdirect.com'

#region category parser test

# category_parser = CategoryPageParser(base_url)

# category_links = category_parser.parse(page_text)

# print(category_links)

#endregion

#region diagram parser test

# with open('/home/daniel/documents/selenium_test_project/parts-direct-scraper/example_htmls/diagrams_page.html') as f:
#     page_text = f.read()

# additional_vars = {
#     'page_url': 'page_url',
#     'base_car_url': 'base_car_url',
#     'category_page_url': 'category_page_url'
# }
# diagram_page_parser = DiagramPageParser(base_url)

# page_diagrams, part_list = diagram_page_parser.parse(page_text, additional_vars)

# print(page_diagrams)

#endregion

#region part parser test
with open('/home/daniel/documents/selenium_test_project/parts-direct-scraper/example_htmls/part_page.html') as f:
    page_text = f.read()

part_page_parser = PartPageParser(base_url)

part = part_page_parser.parse(page_text)
print(part)

#endregion
