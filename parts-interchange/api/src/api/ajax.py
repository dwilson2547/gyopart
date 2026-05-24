from flask import Blueprint, request

ajax_blueprint = Blueprint('ajax', __name__)

@ajax_blueprint.route('/ajax')
def ajax():
    year = request.args.get('year_id')
    make = request.args.get('make_id')
    model = request.args.get('model_id')
    trim = request.args.get('trim_id')
    engine = request.args.get('engine_id')
