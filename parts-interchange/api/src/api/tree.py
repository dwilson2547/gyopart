from flask import Blueprint, current_app, jsonify, request
from models import db, Year, Make, Model, Trim, Engine, Part, Diagram, DiagramParts, Image, PartImages, Category, SubCategory, Car, Manufacturer, car_parts
import base64

tree_blueprint = Blueprint('tree', __name__)

@tree_blueprint.route('/years', methods=['GET'])
def get_years():
    yrs = db.session.query(Year).order_by(Year.name.desc()).all()
    return [yr.as_dict() for yr in yrs]

@tree_blueprint.route('/makes', methods=['GET'])
def get_makes():
    if 'year_id' not in request.args:
        return 'Expected year_id as query parameter but it was not found', 400
    
    try:
        year_id = int(request.args['year_id'])
    except:
        return 'Failed to parse year_id, expected a number', 400
    
    subquery = db.session.query(Car.make_id).filter(Car.year_id == year_id).distinct()
    rows = db.session.query(Make).filter(Make.id.in_(subquery))
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/models', methods=['GET'])
def get_models():

    if 'year_id' not in request.args:
        return 'Expected year_id as query parameter but it was not found', 400
    if 'make_id' not in request.args:
        return 'Expected make_id as query parameter but it was not found', 400
    
    try:
        year_id = int(request.args['year_id'])
        make_id = int(request.args['make_id'])
    except:
        return 'Failed to parse id query parameter, expected a number', 400
    
    subquery = db.session.query(Car.model_id).filter(Car.year_id == year_id, Car.make_id == make_id).distinct()
    rows = db.session.query(Model).filter(Model.id.in_(subquery))
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/trims', methods=['GET'])
def get_trims():
    if 'year_id' not in request.args:
        return 'Expected year_id as query parameter but it was not found', 400
    if 'make_id' not in request.args:
        return 'Expected make_id as query parameter but it was not found', 400
    if 'model_id' not in request.args:
        return 'Expected model_id as query parameter but it was not found', 400
    try:
        year_id = int(request.args['year_id'])
        make_id = int(request.args['make_id'])
        model_id = int(request.args['model_id'])
    except:
        return 'Failed to parse id query parameter, expected a number', 400
    
    subquery = db.session.query(Car.trim_id).filter(Car.year_id == year_id, Car.make_id == make_id, Car.model_id == model_id).distinct()
    rows = db.session.query(Trim).filter(Trim.id.in_(subquery))
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/engines', methods=['GET'])
def get_engines():

    if 'year_id' not in request.args:
        return 'Expected year_id as query parameter but it was not found', 400
    if 'make_id' not in request.args:
        return 'Expected make_id as query parameter but it was not found', 400
    if 'model_id' not in request.args:
        return 'Expected model_id as query parameter but it was not found', 400
    if 'trim_id' not in request.args:
        return 'Expected trim_id as query parameter but it was not found', 400
    try:
        year_id = int(request.args['year_id'])
        make_id = int(request.args['make_id'])
        model_id = int(request.args['model_id'])
        trim_id = int(request.args['trim_id'])
    except:
        return 'Failed to parse id query parameter, expected a number', 400
    
    subquery = db.session.query(Car.engine_id).filter(Car.year_id == year_id, Car.make_id == make_id, Car.model_id == model_id, Car.trim_id == trim_id).distinct()
    rows = db.session.query(Engine).filter(Engine.id.in_(subquery))
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/cars', methods=['GET'])
def get_cars():

    if 'year_id' not in request.args:
        return 'Expected year_id as query parameter but it was not found', 400
    if 'make_id' not in request.args:
        return 'Expected make_id as query parameter but it was not found', 400
    if 'model_id' not in request.args:
        return 'Expected model_id as query parameter but it was not found', 400
    if 'trim_id' not in request.args:
        return 'Expected trim_id as query parameter but it was not found', 400
    if 'engine_id' not in request.args:
        return 'Expected engine_id as query parameter but it was not found', 400
    try:
        year_id = int(request.args['year_id'])
        make_id = int(request.args['make_id'])
        model_id = int(request.args['model_id'])
        trim_id = int(request.args['trim_id'])
        engine_id = int(request.args['engine_id'])
    except:
        return 'Failed to parse id query parameter, expected a number', 400
    
    rows = db.session.query(Car).filter(Car.year_id == year_id, Car.make_id == make_id, Car.model_id == model_id, Car.trim_id == trim_id, Car.engine_id == engine_id)
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/search-parts', methods=['GET'])
def search_parts():

    if 'car_id' not in request.args:
        return 'Expected car_id as query parameter but it was not found', 400
    if 'keyword' not in request.args:
        return 'Expected keyword as query parameter but it was not found', 400
    
    try:
        car_id = int(request.args['car_id'])
        keyword = base64.b64decode(request.args['keyword']).decode('utf-8')
    except:
        return 'Failed to parse query parameter, expected a number and a base64 encoded string', 400

    # part_ids = db.session.query(car_parts.columns['part_id']).filter(car_parts.columns['car_id'] == car_id).subquery()
    # parts = db.session.query(Part).filter(Part.id.in_(part_ids), Part.title.contains(str(keyword))).all()

    rows = db.session.query(Part).join(car_parts).join(Car).filter(Car.id == car_id).filter(Part.title.contains(str(keyword))).all()
    return [row.as_dict() for row in rows]

@tree_blueprint.route('/parts', methods=['GET'])
def get_parts():

    if 'car_id' not in request.args:
        return 'Expected car_id as query parameter but it was not found', 400

    try:
        car_id = int(request.args['car_id'])
    except:
        return 'Failed to parse query parameter, expected a number and a base64 encoded string', 400

    rows = db.session.query(Part).join(car_parts).join(Car).filter(Car.id == car_id).all()
    return [row.as_dict() for row in rows]