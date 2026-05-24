from flask import Blueprint, request
from models import db, Feedback
from util.validator import Validator, Validation, ValidationEntry, ValidationRule


feedback_blueprint = Blueprint('feedback', __name__)

@feedback_blueprint.route('/', methods=['POST'])
def post_feedback():
    """
    request example: {
        'name': str,
        'email': str,
        'comments': str
    }
    """
    payload = request.json
    validator = Validator([
        ValidationEntry('name', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('name', ValidationRule(Validation.MAXLEN, 250)),
        ValidationEntry('email', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('email', ValidationRule(Validation.MAXLEN, 250)),
        ValidationEntry('comments', ValidationRule(Validation.TYPE, str)),
        ValidationEntry('comments', ValidationRule(Validation.MAXLEN, 2000))
    ])
    results = validator.check(payload)

    if results['pass']:
        fb = Feedback(
            name=payload['name'],
            email=payload['email'],
            comments=payload['comments']
        )
        db.session.add(fb)
        db.session.commit()
        return {'status': 'ok'}, 200
    else:
        return results['failures'], 400