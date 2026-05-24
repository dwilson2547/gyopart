from flask import Blueprint, current_app, jsonify, request
from models import db, Year, Make, Model, Trim, Engine, Part, Diagram, DiagramParts, Image, PartImages, Category, SubCategory, Car, Manufacturer, car_parts, PartImages
from util.validator import Validator, Validation, ValidationEntry, ValidationRule
from sqlalchemy.orm import contains_eager

import json
import os

parts_blueprint = Blueprint('part', __name__)

@parts_blueprint.route('/parts', methods=['POST'])
def get_parts():
    """
        
    """
    payload = request.json
    validator = Validator([
        ValidationEntry('car_id', ValidationRule(Validation.TYPE, int), required=True),
        # ValidationEntry('page', ValidationRule(Validation.TYPE, int), required=True),
        # ValidationEntry('page', ValidationRule(Validation.MIN, 1), required=True),
        ValidationEntry('per_page', ValidationRule(Validation.TYPE, int), required=True),
        ValidationEntry('sort_col', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('filterStr', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('sort_dir', ValidationRule(Validation.OPTION_LIST, ['asc','desc']))
    ])

    results = validator.check(payload)

    if results['pass']:
        query = Part.query.distinct().join(car_parts).join(PartImages).join(Image)
        # query = db.session.query(Part).distinct().options(contains_eager(Part.images)).join(car_parts).join(PartImages).join(Image)
        query = query.filter(car_parts.c.car_id == payload['car_id'])
        if 'filterStr' in list(payload.keys()):
            if payload['filterStr'] != '':
                query = query.filter(Part.description.contains(payload['filterStr']) | Part.title.contains(payload['filterStr']) | Part.part_number.contains(payload['filterStr']) | Part.other_names.contains(payload['filterStr']))
        if 'sort_col' in payload and payload['sort_col']:
            dir = payload['sort_dir'] if payload['sort_dir'] else 'desc'
            if payload['sort_col'] == 'part_number' or payload['sort_col'] == 'sku':
                query = query.order_by(Part.part_number.desc() if dir == 'desc' else Part.part_number.asc())
            elif payload['sort_col'] == 'title':
                query = query.order_by(Part.title.desc() if dir == 'desc' else Part.title.asc())
            elif payload['sort_col'] == 'description':
                query = query.order_by(Part.description.desc() if dir == 'desc' else Part.description.asc())
            query = query
        else:
            query = query.order_by(Part.part_number.desc())

        payload['page'] += 1

        page = query.paginate(page=payload['page'], per_page=payload['per_page'], error_out=False)
        out = {
            'items': parse_part_results(page.items),
            'has_next': page.has_next,
            'has_prev': page.has_prev,
            'next_num': page.next_num,
            'prev_num': page.prev_num,
            'page': page.page,
            'per_page': page.per_page,
            'pages': page.pages,
            'total': page.total
        }
        return out
    else:
        return results['failures'], 400
    
def parse_part_results(results: list):
    output = []
    for part in results:
        p = part.as_dict()
        if len(part.images) > 0:
            p['images'] = []
            for img in part.images:
                img_dict = img.as_dict()
                img_dict['image'] = img.image.as_dict()
                p['images'].append(img_dict)
        output.append(p)
    return output

@parts_blueprint.route('/part/<part_id>', methods=['GET'])
def get_part_info(part_id):
    part = Part.query.filter(Part.id == part_id).one()
    return part.as_dict()

@parts_blueprint.route('/compatible_cars/<part_id>', methods=['POST'])
def get_compatible_cars(part_id):

    payload = request.json
    validator = Validator([
        ValidationEntry('part_id', ValidationRule(Validation.TYPE, int), required=True),
        # ValidationEntry('page', ValidationRule(Validation.TYPE, int), required=True),
        # ValidationEntry('page', ValidationRule(Validation.MIN, 1), required=True),
        ValidationEntry('per_page', ValidationRule(Validation.TYPE, int), required=True),
        ValidationEntry('sort_col', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('filterStr', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('sort_dir', ValidationRule(Validation.OPTION_LIST, ['asc','desc']))
    ])

    results = validator.check(payload)

    if results['pass']:

        payload['page'] += 1

        query = Car.query.distinct().join(car_parts).join(Make).join(Model).join(Trim).join(Engine).join(Year).filter(car_parts.c.part_id == part_id)

        page = query.paginate(page=payload['page'], per_page=payload['per_page'], error_out=False)

        out = {
            'items': parse_car_list(page.items),
            'has_next': page.has_next,
            'has_prev': page.has_prev,
            'next_num': page.next_num,
            'prev_num': page.prev_num,
            'page': page.page,
            'per_page': page.per_page,
            'pages': page.pages,
            'total': page.total
        }

        return out

    else:
        return results['failures'], 400

def parse_car_list(results: list):
    output = []
    for car in results:
        c = car.as_dict()
        c['make'] = car.make.as_dict()
        c['model'] = car.model.as_dict()
        c['year'] = car.year.as_dict()
        c['engine'] = car.engine.as_dict()
        c['trim'] = car.trim.as_dict()
        output.append(c)
    return output