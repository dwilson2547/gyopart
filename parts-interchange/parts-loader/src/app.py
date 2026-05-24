from models import Base, PartImages, DiagramParts, Category, SubCategory, Diagram, Image, Manufacturer, Part, Year, Make, Model, Trim, Engine, Car, Feedback, car_categories, car_diagrams, car_parts
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import json
import os
from config import get_db_url
from car_configs import CarConfigs
from typing import List
from io import StringIO
from html.parser import HTMLParser



root_data_path: str = '/home/daniel/kube-data/pvc-c9c3aff2-5e41-46eb-bce5-3192026b2cb5'
split_years_dir: str = 'years'
parts_file_name = 'parts.json'
images_file_name = 'imgs.json'
tree_file_name = 'tree.json'
split_tree_file_name = 'tree_split.json'
images_directory = 'images'

#region HTML Cleaner

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = StringIO()
    def handle_data(self, d):
        self.text.write(d)
    def get_data(self):
        return self.text.getvalue()

#endregion

def proper_case_string(input: str):
    return input[0].upper() + input[1:].lower()

def create_generations(tree: dict):

    # Doesn't really work with the data I have unfortunately 
    gens = {}
    gen_counter = 0

    for year, year_val in tree.items():
        for make, make_val in year_val['makes'].items():
            for model, model_val in make_val['models'].items():
                for trim, trim_val in model_val['trims'].items():
                    for engine, engine_val in trim_val['engines'].items():
                        part_set = set(engine_val['parts'])
                        car_gen = None
                        for gen_id, gen_set in gens.items():
                            if part_set == gen_set:
                                car_gen = gen_id
                                engine_val['generation'] = gen_id
                        if car_gen == None:
                            gens[gen_counter] = part_set
                            engine_val['generation'] = gen_counter
                            gen_counter += 1
    return gens

def split_tree_on_years(tree_file: str, year_dir_path: str):
    tree = {}
    with open(tree_file) as f:
        tree = json.load(f)
    new_tree = {}
    if not os.path.exists(year_dir_path):
        os.mkdir(year_dir_path)
    for year, year_val in tree.items():
        if type(year_val) == str:
            continue
        elif type(year_val) == dict:
            year_file = year + '.json'
            with open(os.path.join(year_dir_path, year_file), 'w') as f:
                f.write(json.dumps({year: year_val}))
            new_tree[year] = os.path.join(split_years_dir, year_file)
    return new_tree

def create_session():
    db_user = 'test'
    db_pass = 'dw31571102'
    db_url = 'localhost:3306/parts-interchange'

    engine = create_engine(get_db_url(db_user, db_pass, db_url))

    Base.metadata.create_all(engine)

    session = Session(engine)
    return session

#region Manufacturer

def get_manufacturer_map(session: Session):
    rows = session.query(Manufacturer).all()
    mfr_map = {mfr.name.lower(): mfr for mfr in rows}
    return mfr_map

def process_manufacturer(make: str, mfr_map: dict, config_data: dict, session: Session):
    if not make.lower() in mfr_map:
        new_mfr = create_mfr(make, config_data, session)
        mfr_map[make.lower()] = new_mfr
    return mfr_map

def create_mfr(name: str, config_data: dict, session: Session):
    new_mfr = Manufacturer(name=proper_case_string(name), base_url=config_data['base_url'])
    session.add(new_mfr)
    session.commit()
    return new_mfr

#endregion

#region Image Processing

def load_images(session: Session, mfr: Manufacturer):
    images = session.query(Image).filter(Image.manufacturer_id == mfr.id)
    image_map = {img.name: img for img in images}
    return image_map

def process_images(session: Session, image_map: dict, manufacturer: Manufacturer, make: str, images_file: str):

    with open(images_file) as img_f:
        images = json.load(img_f)

    img_names = list(images.keys())

    for i, item in enumerate(img_names):
        if i % 10000 == 0:
            print(f'Ingesting image {i + 1} out of {len(img_names)}')

        if item in image_map:
            continue

        image = images[item]
        # url, alt, saved, uploaded

        if 'saved' not in image:
            image['saved'] = True

        img = Image(
            name=item,
            bucket_path=f'{make}/images/{item}',
            url=image['url'],
            alt_text=image['alt'],
            saved=image['saved'] if 'saved' in image else True,
            uploaded=image['uploaded'] if 'uploaded' in image else False,
            manufacturer=manufacturer
        )
        image_map[item] = img

        session.add(img)

        if i % 1000 == 0:
            session.flush()
    session.commit()

    return image_map

#endregion

#region Parts Processing

def load_parts(session: Session, mfr: Manufacturer):
    parts = session.query(Part).filter(Part.manufacturer_id == mfr.id)
    part_map = {part.part_number: part for part in parts}
    return part_map

def clean_title(title: str, part_num: str):
    try:
        return '-'.join(title.replace(part_num, '').split('-')[:-1]).strip()
    except Exception as ex:
        print(ex)
        return title
    
# def clean_html_tags(input: str):
#     strippables = ['<p>', '</p>', '<b>', '</b>', '<br>', '<br />', '<strong>', '</strong>', '</em>', '<em>', '<li>', '</li>', '<ul>', '</ul>']
#     input = input.replace('<p>', '')
#     input = input.replace('</p>', '')
#     input = input.replace('<b>', '')
#     input = input.replace('</b>', '')
#     input = input.replace('<br>', '')
#     input = input.replace('<br />', '')
#     input = input.replace('<strong>', '')
#     input = input.replace('</strong>', '')
#     return input

def clean_html_tags(input: str):
    if input is None:
        return None
    s = MLStripper()
    s.feed(input)
    return s.get_data()

def process_parts(session: Session, part_map: dict, manufacturer: Manufacturer, parts_file: str, image_map: dict):
    changes = False

    with open(parts_file) as p_f:
        parts = json.load(p_f)

    part_numbers = list(parts.keys())

    for i, p_n in enumerate(part_numbers):
        if i % 10000 == 0:
            print(f'Ingesting part {i + 1} out of {len(part_numbers)}')
        part = parts[p_n]

        if p_n in part_map:
            continue
        
        try:
            p = Part(
                part_number=p_n,
                title=clean_title(part['title'], p_n),
                url=part['url'],
                other_names=part['also_known_as'] if 'also_known_as' in part else None,
                description=clean_html_tags(part['description']) if 'description' in part else None,
                positions=part['positions'] if 'positions' in part else None,
                msrp=part['msrp'] if 'msrp' in part else None,
                notes=part['notes'] if 'notes' in part else None,
                applications=part['applications'] if 'applications' in part else None,
                hazmat=part['is_hazmat'] if 'is_hazmat' in part else None
            )
        except Exception as ex:
            print(ex)
            print('Error when adding part')
            print(p_n)
            print(part)
            continue

        p.manufacturer = manufacturer

        session.add(p)
        changes = True

        processed_images = []
        
        img_keys = ['main', 'preview', 'thumb']
        
        for img_entry in part['images']:
            for img_key in img_keys:
                if img_key in img_entry and img_entry[img_key] is not None:
                    try:
                        img_name = img_entry[img_key]['url'].split('/')[-1]
                        if img_name in processed_images:
                            # Image has already been ingested for this part, somehow we got a duplicate so skip it
                            continue
                        caption = img_entry['caption']
                        if img_name in image_map:
                            pi = PartImages(part_image_text=caption, image=image_map[img_name], part=p)
                            session.add(pi)
                            # p.images.append(image_map[img])
                        else:
                            # Shouldn't be possible but
                            new_img = Image(name=img_name, saved=False, uploaded=False)
                            pi = PartImages(part_image_text=caption, image=new_img, part=p)
                            p.images.append(pi)
                            print(f'Unexpected Image found: {img_name}')
                        processed_images.append(img_name)
                    except Exception as ex:
                        print(img_key)
                        print(img_entry)
                        raise ex

        part_map[p_n] = p

        if i % 1000 == 0:
            session.flush()
    if changes:
        session.commit()
    return part_map

#endregion

#region Car Processing

def format_print_msg(message, level = 0):
    print('    ' * level + message)

def build_car_tree(cars: List[Car]):
    tree = {}

    for car in cars:
        year = car.year_id
        make = car.make_id
        model = car.model_id
        trim = car.trim_id
        engine = car.engine_id
        if not year in tree:
            tree[year] = {}
        if not make in tree[year]:
            tree[year][make] = {}
        if not model in tree[year][make]:
            tree[year][make][model] = {}
        if not trim in tree[year][make][model]:
            tree[year][make][model][trim] = {}
        if not engine in tree[year][make][model][trim]:
            tree[year][make][model][trim][engine] = True
    return tree

def process_cars(session: Session, tree_file: str, manufacturer: Manufacturer, image_map: dict, part_map: dict):
    with open(tree_file) as t_f:
        tree = json.load(t_f)
    year_map = {year.name: year for year in session.query(Year).all()}
    make_map = {make.select_value: {'make': make, 'models': {x.select_value: x for x in make.models}} for make in session.query(Make).all()}
    trim_map = {trim.select_value: trim for trim in session.query(Trim).all()}
    engine_map = {engine.select_value: engine for engine in session.query(Engine).all()}
    cat_map = {}

    categories = session.query(Category).all()
    for row in categories:
        cat_map[row.name] = {
            'cat': row,
            'subs': {sub.name: sub for sub in row.sub_categories}
        }

    cars = session.query(Car).filter(Car.manufacturer_id == manufacturer.id)
    existing_car_tree = build_car_tree(cars)

    for year, year_file_name in tree.items():
        year_data = {}
        year_file_full_path = os.path.join(root_data_path, manufacturer.name.lower(), year_file_name)
        with open(year_file_full_path, 'r') as f:
            year_data = json.load(f)
        format_print_msg(str(year), 0)
        if year not in year_map:
            yr = Year(name=year)
            session.add(yr)
            year_map[year] = yr
        yr = year_map[year]

        makes = list(year_data[year]['makes'].keys())
        for make in makes:
            format_print_msg(make, 1)
            make_record = year_data[year]['makes'][make]
            if make not in make_map:
                mk = Make(
                    name=make_record['ui'],
                    select_value = make,
                    start_year = make_record['start_year'],
                    end_year = make_record['end_year']
                )
                session.add(mk)
                make_map[make] = {'make': mk, 'models': {}}
            mk = make_map[make]['make']

            models = list(make_record['models'].keys())
            for model in models:
                format_print_msg(model, 2)
                model_record = make_record['models'][model]
                if model not in make_map[make]['models']:
                    mdl = Model(
                        name=model_record['ui'],
                        select_value=model
                    )
                    mdl.make = mk

                    session.add(mdl)
                    make_map[make]['models'][model] = mdl
                mdl = make_map[make]['models'][model]

                trims = list(model_record['trims'].keys())
                for trim in trims:
                    format_print_msg(trim, 3)
                    trim_record = model_record['trims'][trim]
                    if not trim in trim_map:
                        trm = Trim(
                            name=trim_record['ui'],
                            select_value=trim
                        )
                        session.add(trm)
                        trim_map[trim] = trm
                    trm = trim_map[trim]

                    engine_names = list(trim_record['engines'].keys())
                    for engine_name in engine_names:
                        format_print_msg(engine_name, 4)
                        engine_record = trim_record['engines'][engine_name]

                        if not engine_name in engine_map:
                            eng = Engine(
                                name=engine_record['ui'],
                                select_value=engine_name
                            )
                            session.add(eng)
                            engine_map[engine_name] = eng
                        eng = engine_map[engine_name]

                        # Check if this car has already been processed
                        try:
                            n = existing_car_tree[yr.id][mk.id][mdl.id][trm.id][eng.id]
                            print('car already ingested')
                            continue
                        except KeyError as ex:
                            pass

                        if not 'diagrams' in engine_record:
                            engine_record['diagrams'] = []

                        diagrams = engine_record['diagrams']

                        if not 'parts' in engine_record:
                            engine_record['parts'] = []

                        parts = engine_record['parts']
                        car_id = engine_record['car_id']
                        vehicle_id = engine_record['vehicle_id']
                        car_url = engine_record['page_url']

                        car = Car(base_url=car_url, car_id=car_id, vehicle_id=vehicle_id)
                        car.year = yr
                        car.make = mk
                        car.model = mdl
                        car.trim = trm
                        car.engine = eng
                        car.manufacturer = manufacturer
                        session.add(car)

                        # Map diagrams to car and handle categories
                        for entry in diagrams:
                            diagram_page_url = entry['diagram_page_url']
                            for diagram in entry['diagrams']:

                                if not car.base_url:
                                    car.base_url = diagram['base_car_url']

                                img_name = diagram['img']
                                category_name = diagram['category_name']
                                category_url = diagram['category_link']

                                cat_longname = category_url.split('/')[-1]
                                if not cat_longname:
                                    cat_longname = category_url.split('/')[-2]
                                cats = cat_longname.split('--')
                                if len(cats) == 2:
                                    main_cat = cats[0].strip()
                                    sub_cat = cats[1].strip()

                                    # If new main category, add to hashmap along with sub category
                                    if not main_cat in cat_map:
                                        c = Category(name=main_cat)
                                        s = SubCategory(name=sub_cat)
                                        c.sub_categories.append(s)
                                        session.add(c)
                                        cat_map[main_cat] = {
                                            'cat': c,
                                            'subs': {sub_cat: s}
                                        }
                                    category = cat_map[main_cat]['cat']
                                    if not sub_cat in cat_map[main_cat]['subs']:
                                        s = SubCategory(name=sub_cat)
                                        category.sub_categories.append(s)
                                        session.add(s)
                                        cat_map[main_cat]['subs'][sub_cat] = s
                                    sub_category = cat_map[main_cat]['subs'][sub_cat]

                                elif len(cats) == 1:
                                    main_cat = cats[0]
                                    if not main_cat in cat_map:
                                        c = Category(name=main_cat)
                                        session.add(c)
                                        cat_map[main_cat] = {
                                            'cat': c,
                                            'subs': {}
                                        }
                                    category = c
                                else:
                                    print('abnormal category found')

                                if img_name in image_map:
                                    diagram_image = image_map[img_name]

                                d = Diagram(base_car_url=diagram['base_car_url'], category_url=category_url)
                                d.image = diagram_image
                                if sub_category:
                                    d.sub_category = sub_category
                                elif category:
                                    d.category = category
                                else:
                                    print('no category diagram found')

                                session.add(d)

                                diagram_parts_entries = {}

                                for idx in list(diagram['parts'].keys()):
                                    for part_num in diagram['parts'][idx]:
                                        if not part_num in parts:
                                            print('found part number that doesnt exist: ' + part_num)
                                            continue

                                        if part_num in diagram_parts_entries:
                                            existing_record = diagram_parts_entries[part_num]
                                            if idx in existing_record.part_index.split(','):
                                                # Duplicate record found, skip
                                                continue
                                            else:
                                                existing_record.part_index = existing_record.part_index + ',' + idx.strip()
                                                # Duplicate record found with different index, combine entries
                                                continue

                                        dp = DiagramParts(part_index=idx.strip())
                                        dp.part = part_map[part_num]

                                        diagram_parts_entries[part_num] = dp

                                        d.parts.append(dp)

                        # Map parts to car
                        for part in parts:
                            if part in part_map:
                                car.parts.append(part_map[part])

        session.commit()

#endregion

def start_ingestion():
    session = create_session()
    mfr_map = get_manufacturer_map(session)
    for make, data in CarConfigs.configs.items():
        if 'skip' in data:
            if data['skip']:
                continue

        images_file = os.path.join(root_data_path, make.lower(), images_file_name)
        parts_file = os.path.join(root_data_path, make.lower(), parts_file_name)
        tree_file = os.path.join(root_data_path, make.lower(), tree_file_name)
        split_tree_file = os.path.join(root_data_path, make.lower(), split_tree_file_name)

        if not os.path.exists(split_tree_file):
            year_dir_path = os.path.join(root_data_path, make.lower(), split_years_dir)
            new_tree = split_tree_on_years(tree_file, year_dir_path)
            with open(split_tree_file, 'w') as f:
                f.write(json.dumps(new_tree))

        mfr_map = process_manufacturer(make, mfr_map, data, session)

        manufacturer_rec = mfr_map[make.lower()]
        image_map = load_images(session, manufacturer_rec)
        image_map = process_images(session, image_map, manufacturer_rec, make, images_file)

        part_map = load_parts(session, manufacturer_rec)
        part_map = process_parts(session, part_map, manufacturer_rec, parts_file, image_map)

        process_cars(session, split_tree_file, manufacturer_rec, image_map, part_map)



if __name__ == '__main__':
    start_ingestion()

