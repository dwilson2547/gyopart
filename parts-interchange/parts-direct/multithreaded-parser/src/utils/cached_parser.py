import json
import logging

from bs4 import BeautifulSoup as bs
from bs4.element import Tag
from .exceptions import (Browser403Error, Browser429Error,
                              InternetDownError)

log = logging.getLogger()


class CachedParser:
    """
    Parser of cached pages
    """

    base_url: str

    def __init__(self, base_url: str):
        self.base_url = base_url

    def parse_category_page(self, page_text: str):
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

        subcategory_links_selector = 'div.oem-sidebar-categories div.category-parts div.card.parts a'

        soup = bs(page_text, 'html.parser')

        subcategory_link_objs = soup.select(subcategory_links_selector)

        subcategory_links = [x['href'] for x in subcategory_link_objs]
        # Create dict and filter page references
        subcategory_links = [{'url': self.base_url + x, 'done': False} for x in subcategory_links if x[0] != '#']

        return subcategory_links

    def parse_diagram_page(self, page_text: str, additional_vars: dict, cached: bool):
        """
        Returns structure containing all diagrams with part mappings scraped
        """
        part_category_selector = '.page-bread-crumbs a:nth-of-type(3)'

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
        sub_cat_link = soup.select_one(part_category_selector)

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
        part_diagram_name = part_diagram_url.split('/')[-1]

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

    def parse_part(self, page_text: str):
        """
        Parses part data from script tag that contains json
        """
        soup = bs(page_text, 'html.parser')

        product_data = soup.find('script', {'id': 'product_data'})

        if product_data:
            return json.loads(product_data.text)
        log.warning('Part parsing failed, no script tag found with id product_data')
        return {
                'title': '',
                'images': [],
                'details': {},
                'fitment': [],
                'skipped': True
            }

    def check_page(self, page_text: str):
        """
        Checks to see if page is valid
        """
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
        """
        Checks to see if cached page is valid
        """
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
