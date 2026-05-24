from flask import Blueprint, current_app, jsonify, request
from models import db, Year, Make, Model, Trim, Engine, Part, Diagram, DiagramParts, Image, PartImages, Category, SubCategory, Car, Manufacturer

mfr_blueprint = Blueprint('manufacturer', __name__)

@mfr_blueprint.route('/', methods=['GET'])
def get_manufacturers(): 
    mfrs = db.session.query(Manufacturer).all()
    return [mfr.as_dict() for mfr in mfrs]

@mfr_blueprint.route('/<id>', methods=['GET'])
def get_manufacturer(id):
    mfr = db.session.query(Manufacturer).filter(Manufacturer.id == id).first()
    if mfr:
        return mfr.as_dict()
    else:
        return {}

@mfr_blueprint.route('/', methods=['POST'])
def add_manufacturer():
    payload = request.form
    if not request.form:
        print('no form')
        if not request.json:
            return 'Unable to process request, no form or json present', 400
        else:
            payload = request.json
    
    if 'name' not in payload or 'base_url' not in payload:
        return 'Unable to create new manufacturer, name or base_url was missing from payload', 400
    
    mfr = Manufacturer(name=payload['name'], base_url=payload['base_url'])
    db.session.add(mfr)
    return mfr.as_dict()

@mfr_blueprint.route('/<id>', methods=['POST'])
def edit_manufacturer(id):
    payload = request.form
    if not request.form:
        print('no form')
        if not request.json:
            return 'Unable to process request, no form or json present', 400
        else:
            payload = request.json

    if 'name' not in payload or 'base_url' not in payload:
        return 'Unable to create new manufacturer, name or base_url was missing from payload', 400
    
    mfr = db.session.query(Manufacturer).filter(Manufacturer.id == id).first()
    if not mfr:
        return 'Cannot update manufacturer, id not found', 400
    mfr.name = payload['name']
    mfr.base_url = payload['base_url']
    db.session.commit()
    return mfr.as_dict()

@mfr_blueprint.route('/<id>', methods=['DELETE'])
def delete_manufacturer(id):
    mfr = db.session.query(Manufacturer).filter(Manufacturer.id == id).first()
    if not mfr:
        return 'Cannot delete manufacturer, id not found', 400
    mfr.delete()
    db.session.commit()
    return 'ok', 200

