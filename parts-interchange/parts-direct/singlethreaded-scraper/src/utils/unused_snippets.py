
from bs4 import BeautifulSoup as bs
import json
import re

def extract_data_from_script_tag_variable(page_text):
    print('diagram page parser')

    soup = bs(page_text)

    script_tags = soup.find_all('script', {'type': 'text/javascript'})

    for script_tag in script_tags:
        json_text_data = re.findall(r"tracking = ({.*?});", script_tag.text)
        if json_text_data:
            try:
                out_data = json.loads(json_text_data[0])
                return out_data
            except:
                continue

    return None