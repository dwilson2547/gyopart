import json
import re

from bs4 import BeautifulSoup as bs
from bs4.element import Tag
from utils.Constants import PageType
from utils.Exceptions import Browser403Error, Browser429Error, InternetDownError


class CachedParser:

    def __init__(self, base_url: str):
        self.parser_lookup: dict[str, CachedPageParser] = {
            PageType.CATEGORIES: CategoryPageParser(base_url),
            PageType.DIAGRAMS: DiagramPageParser(base_url),
            PageType.PART: PartPageParser(base_url)
        }

    def parse_cached_page(self, page_text: str, pageType: str, additional_vars: dict = None, cached: bool = None):

        if pageType in self.parser_lookup:
            parserClass = self.parser_lookup[pageType]
        else:
            raise KeyError(f'Unknown page type provided, please see Constants.PageType for available page types')

        return parserClass.parse(page_text, additional_vars, cached)

    def check_page(self, page_text: str):
        soup = bs(page_text, 'html.parser')
        title = soup.find('title')
        header = soup.find('h1')
        search_text = title.text if title else '' + header.text if header else ''
        main_div = soup.find('div', {'class': 'main'})
        if "403" in search_text and "forbidden" in search_text.lower() and not main_div:
            print('403 code received, stopping now')
            raise Browser403Error('403 code received')
        if "429" in search_text and 'requests' in search_text.lower() and not main_div:
            print('429 code received')
            raise Browser429Error('429 code received')
        if "No Internet" in search_text and not main_div:
            raise InternetDownError()
        if 'Page Not Found' in search_text:
            return False
        else:
            return True

    def check_cached_page(self, page_text: str):
        soup = bs(page_text, 'html.parser')
        title = soup.find('title')
        header = soup.find('h1')
        search_text = title.text if title else '' + header.text if header else ''
        main_div = soup.find('div', {'class': 'main'})
        if "403" in search_text and "forbidden" in search_text.lower() and not main_div:
            return False
        if "429" in search_text and 'requests' in search_text.lower() and not main_div:
            return False
        if "No Internet" in search_text and not main_div:
            return False
        if 'Page Not Found' in search_text:
            return False
        else:
            return True


class CachedPageParser:

    base_url: str

    def parse(self, page_text: str, additional_vars: dict, cached: bool):
        pass

class CategoryPageParser(CachedPageParser):

    SUBCATEGORY_LINKS_SELECTOR = 'div.oem-sidebar-categories div.category-parts div.card.parts a'

    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def parse(self, page_text: str, additional_vars = None, cached: bool = None):
        """
        Category Page Parser, returns list of part categories for a car page

        filter page references explanation:
        Category pages contain primary and secondary categories, a primary
        category might be Brakes whereas a secondary category could be Brake Drum.
        The 'Brake' link doesn't actually go anywhere, it just expands the accordion
        to make the 'Brake Drum' option visible. For this reason, primary categories are
        filtered out so we only get navigable? links. The primary and secondary categories
        are parsed later on from the url of the diagram page
        """

        soup = bs(page_text, 'html.parser')

        subcategory_link_objs = soup.select(self.SUBCATEGORY_LINKS_SELECTOR)
        
        subcategory_links = [x['href'] for x in subcategory_link_objs]
        # Create dict and filter page references
        subcategory_links = [{'url': self.base_url + x, 'done': False} for x in subcategory_links if x[0] != '#']

        return subcategory_links

class DiagramPageParser(CachedPageParser):

    PART_CATEGORY_SELECTOR = '.page-bread-crumbs a:nth-of-type(3)'
    
    def __init__(self, base_url):
        self.base_url = base_url

    def parse(self, page_text: str, additional_vars: dict, cached: bool):
        base_car_url = additional_vars['base_car_url']
        category_page_url = additional_vars['category_page_url']
        
        parsed_diagrams = {
            'diagram_page_url': category_page_url,
            'diagrams': [],
            'done': False,
            'skipped': False
        }
        part_list = {}

        soup = bs(page_text, 'html.parser')

        # Get category name
        sub_cat_link = soup.select_one(self.PART_CATEGORY_SELECTOR)

        # If category name link is missing something's wrong, skip for now
        if not sub_cat_link:
            parsed_diagrams['done'] = True
            parsed_diagrams['skipped'] = True
            return parsed_diagrams, part_list
        
        sub_cat_name = sub_cat_link.text.strip()

        diagram_groups = soup.find_all('div', {'class': 'part-group-container'})

        print('Building diagrams for category: ' + sub_cat_name + ' Cached: ' + str(cached))

        for i, diagram_group in enumerate(diagram_groups):
            related_parts = False
            if i+1 == len(diagram_groups):
                related_parts = self._check_related_parts(diagram_group)

            if related_parts:
                related_parts = self._parse_related_parts(diagram_group)
                for part in related_parts:
                    if part['part_number'] not in part_list:
                        part_list[part['part_number']] = part['url']
            else:
                diagram, group_part_list = self._parse_group_parts(diagram_group, sub_cat_name, base_car_url, category_page_url)
                parsed_diagrams['diagrams'].append(diagram)
                for part in group_part_list:
                    if part['part_number'] not in part_list:
                        part_list[part['part_number']] = part['url']
    
        parsed_diagrams['done'] = True

        return parsed_diagrams, part_list

    def _check_related_parts(self, diagram_group: Tag):
        header = diagram_group.find('h2', {'class': 'related_parts'})
        if not header:
            return False
        return True
            
    def _parse_related_parts(self, diagram_group: Tag):
        related_parts = []
        
        part_rows = diagram_group.select('.all-parts-table-container .catalog-product')

        for row in part_rows:
            part_number_link = row.select_one('.product-details-col .product-partnum a')
            part_number = part_number_link.text.strip()
            part_link = part_number_link['href']
            related_parts.append({'part_number': part_number, 'url': self.base_url + part_link if self.base_url not in part_link else part_link})
        
        return related_parts

    def _parse_group_parts(self, diagram_group: Tag, sub_cat_name: str, base_car_url: str, category_page_url: str):
        part_diagram_img = diagram_group.find('img', {'class': 'parts-diagram'})
        part_list = []

        if not part_diagram_img:
            print('Part diagram not found, skipping')
            return {
                'img': '',
                'img_url': '',
                'alt_text': '',
                'category_name': sub_cat_name,
                'base_car_url': base_car_url,
                'category_link': category_page_url,
                'skipped': True,
                'parts': {}
            }, part_list
        part_diagram_url = part_diagram_img['src']
        part_diagram_name = self._get_file_name(part_diagram_url)

        diagram = {
            'img': part_diagram_name,
            'img_url': part_diagram_url,
            'alt_text': part_diagram_img['alt'],
            'category_name': sub_cat_name,
            'base_car_url': base_car_url,
            'category_link': category_page_url,
            'parts': {}
        }

        part_rows = diagram_group.select('.all-parts-table-container .catalog-product')

        for row in part_rows:
            diagram_reference_code = row.select_one('.reference-code-col').text
            part_num_link = row.select_one('.product-details-col .product-partnum a')
            part_num = part_num_link.text.strip()

            if diagram_reference_code in diagram['parts']:
                diagram['parts'][diagram_reference_code].append(part_num)
            else:
                diagram['parts'][diagram_reference_code] = [part_num]
            part_list.append({'part_number': part_num, 'url': self.base_url + part_num_link['href'] if self.base_url not in part_num_link['href'] else part_num_link['href']})

        return diagram, part_list

    def _get_file_name(self, url: str):
        return url.split('/')[-1]

class PartPageParser(CachedPageParser):

    PART_NAME_SELECTOR = 'div.product-title-module h1'
    PART_DETAILS_SELECTOR = 'div.product-details-module ul.field-list li'
    PART_FITMENT_SELECTOR = 'table.fitment-table'

    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def parse(self, page_text: str, additional_vars: dict = None, cached: bool = None):

        soup = bs(page_text, 'html.parser')

        product_data = soup.find('script', {'id': 'product_data'})

        if product_data:
            parsed_data = json.loads(product_data.text)
        else:
            print('Part parsing failed, no script tag found with id product_data')
            return {
                    'title': '',
                    'images': [],
                    'details': {},
                    'fitment': [],
                    'skipped': True
                }
        
        return parsed_data