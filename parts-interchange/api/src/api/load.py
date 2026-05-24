from flask import Blueprint, current_app
from models import db, Year, Make, Model, Trim, Engine, Part, Diagram, DiagramParts, Image, PartImages, Category, SubCategory, Car, Manufacturer
from api.configs import Configs

import json
import os

current_dir = os.path.dirname(os.path.realpath(__file__))

load_blueprint = Blueprint('load', __name__)

@load_blueprint.route('/<make>')
def load(make):
    print(make)
    # route is deprecated.
    return 'Deprecated endpoint', 410

def begin(make: str):
    """
    Starts the process, moved this to its own function to hopefully prevent memory leaks
    """
    if make in Configs.configs:
        cfg = Configs.get(make)

        mfrs = db.session.query(Manufacturer).all()
        mfr_map = {mfr.name: mfr for mfr in mfrs}

        if not make in mfr_map:
            mfr = Manufacturer(name=make, base_url=cfg['base_url'])

            db.session.add(mfr)
            db.session.commit()
            mfr_map[make] = mfr

        mfr = mfr_map[make]

        data_dir = cfg['data_dir']
        PARTS_FILE = os.path.join(data_dir, 'parts.json')
        IMG_DIR = os.path.join(data_dir, 'images')
        IMAGES_FILE = os.path.join(data_dir, 'imgs.json')
        TREE_FILE = os.path.join(data_dir, 'tree.json')

        image_map = load_images(db, mfr)
        image_map = process_images(db, image_map, mfr, make, IMAGES_FILE, IMG_DIR)

        part_map = load_parts(db, mfr)
        part_map = process_parts(db, part_map, mfr, PARTS_FILE, image_map)

        process_cars(db, TREE_FILE, mfr, image_map, part_map)

    return make

def load_images(db, mfr):
    images = db.session.query(Image).filter(Image.manufacturer_id == mfr.id)
    image_map = {img.name: img for img in images}
    return image_map

def process_images(db, image_map, manufacturer, make, images_file, image_directory):
    bucket_utils = current_app.config['bucket_utils']

    with open(images_file) as img_f:
        images = json.load(img_f)

    img_names = list(images.keys())
    imgs = []

    for i, item in enumerate(img_names):
        if i % 10000 == 0:
            print(f'Ingesting image {i + 1} out of {len(img_names)}')

        if item in image_map:
            continue

        image = images[item]
        # url, alt, saved, uploaded

        if 'saved' not in image:
            image['saved'] = True

        if image['saved']:
            if 'uploaded' not in image or image['uploaded'] == False:
                
                try:
                    bucket_utils.upload_image_to_bucket('part-images', make, item, os.path.join(image_directory, item))
                    image['uploaded'] = True
                except Exception as ex:
                    print(ex)

        img = Image(
            name=item,
            bucket_path=f'{make}/images/{item}',
            url=image['url'],
            alt_text=image['alt'],
            saved=image['saved'] if 'saved' in image else True,
            uploaded=image['uploaded'] if 'uploaded' in image else False,
            manufacturer=manufacturer
        )
        # db.session.add(img)
        imgs.append(img)
        image_map[item] = img

        db.session.add(img)

        if i % 1000 == 0:
            db.session.flush()
    db.session.commit()

    # with open(images_file, 'w') as img_f:
    #     img_f.write(json.dumps(images))

    return image_map

def load_parts(db, mfr):
    parts = db.session.query(Part).filter(Part.manufacturer_id == mfr.id)
    part_map = {part.part_number: part for part in parts}
    return part_map

def process_parts(db, part_map, manufacturer, parts_file, image_map):
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
                title=part['title'],
                url=part['url'],
                other_names=part['also_known_as'] if 'also_known_as' in part else None,
                description=part['description'] if 'description' in part else None,
                positions=part['positions'] if 'positions' in part else None,
                msrp=part['msrp'] if 'msrp' in part else None,
                notes=part['notes'] if 'notes' in part else None,
                applications=part['applications'] if 'applications' in part else None,
                hazmat=part['is_hazmat'] if 'is_hazmat' in part else None
            )
        except:
            print('Error when adding part')
            print(p_n)
            print(part)
            continue

        p.manufacturer = manufacturer

        db.session.add(p)
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
                            db.session.add(pi)
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
            db.session.flush()
    if changes:
        db.session.commit()
    return part_map

def format_print_msg(message, level = 0):
    print('    ' * level + message)

def build_car_tree(cars):
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


def process_cars(db, tree_file, manufacturer, image_map, part_map):
    with open(tree_file) as t_f:
        tree = json.load(t_f)
    year_map = {year.name: year for year in db.session.query(Year).all()}
    make_map = {make.select_value: {'make': make, 'models': {x.select_value: x for x in make.models}} for make in db.session.query(Make).all()}
    trim_map = {trim.select_value: trim for trim in db.session.query(Trim).all()}
    engine_map = {engine.select_value: engine for engine in db.session.query(Engine).all()}
    cat_map = {}

    categories = db.session.query(Category).all()
    for row in categories:
        cat_map[row.name] = {
            'cat': row,
            'subs': {sub.name: sub for sub in row.sub_categories}
        }

    cars = db.session.query(Car).filter(Car.manufacturer_id == manufacturer.id)
    existing_car_tree = build_car_tree(cars)
    
    years = list(tree.keys())

    for year in years:
        format_print_msg(str(year), 0)
        if year not in year_map:
            yr = Year(name=year)
            db.session.add(yr)
            year_map[year] = yr
        yr = year_map[year]

        makes = list(tree[year]['makes'].keys())
        for make in makes:
            format_print_msg(make, 1)
            make_record = tree[year]['makes'][make]
            if make not in make_map:
                mk = Make(
                    name=make_record['ui'],
                    select_value = make,
                    start_year = make_record['start_year'],
                    end_year = make_record['end_year']
                )
                db.session.add(mk)
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

                    db.session.add(mdl)
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
                        db.session.add(trm)
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
                            db.session.add(eng)
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
                        db.session.add(car)

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
                                        db.session.add(c)
                                        cat_map[main_cat] = {
                                            'cat': c,
                                            'subs': {sub_cat: s}
                                        }
                                    category = cat_map[main_cat]['cat']
                                    if not sub_cat in cat_map[main_cat]['subs']:
                                        s = SubCategory(name=sub_cat)
                                        category.sub_categories.append(s)
                                        db.session.add(s)
                                        cat_map[main_cat]['subs'][sub_cat] = s
                                    sub_category = cat_map[main_cat]['subs'][sub_cat]

                                elif len(cats) == 1:
                                    main_cat = cats[0]
                                    if not main_cat in cat_map:
                                        c = Category(name=main_cat)
                                        db.session.add(c)
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

                                db.session.add(d)
                                
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
                                                existing_record.part_index = existing_record.part_index + ',' + idx
                                                # Duplicate record found with different index, combine entries
                                                continue
                                        
                                        dp = DiagramParts(part_index=idx)
                                        dp.part = part_map[part_num]
                                        
                                        diagram_parts_entries[part_num] = dp
                                        
                                        d.parts.append(dp)
                            
                        # Map parts to car
                        for part in parts:
                            if part in part_map:
                                car.parts.append(part_map[part])
                                
        db.session.commit()

