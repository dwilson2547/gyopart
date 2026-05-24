from flask import Flask
from models import db
import os
from minio import Minio
from api.load import load_blueprint
from api.manufacturer import mfr_blueprint
from api.tree import tree_blueprint
from api.parts import parts_blueprint
from api.feedback import feedback_blueprint
import cherrypy
# import logging
# logging.basicConfig()
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

class BucketUtils:

    def __init__(self, url=None, access=None, secret=None, secure=False):
        if not url:
            url = os.getenv('BUCKET_URL')
            url = url.strip() if url else None
        if not access:
            access = os.getenv('BUCKET_ACCESS')
            access = access.strip() if access else None
        if not secret:
            secret = os.getenv('BUCKET_SECRET')
            secret = secret.strip() if secret else None

        self.client = Minio(url,
            access_key=access,
            secret_key=secret,
            secure=secure)

        print(self.client.list_buckets())
        print('BucketUtils Init Successful')

    def upload_image_to_bucket(self, bucket: str, make: str, file_name: str, file_path: str):
        dest_path = f'{make}/images/{file_name}'
        self.client.fput_object(bucket, dest_path, file_path)

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')
    db.init_app(app)

    app.config['bucket_utils'] = None

    app.register_blueprint(load_blueprint, url_prefix='/load')
    app.register_blueprint(mfr_blueprint, url_prefix='/mfr')
    app.register_blueprint(tree_blueprint, url_prefix='/api/tree')
    app.register_blueprint(parts_blueprint, url_prefix='/api/parts')
    app.register_blueprint(feedback_blueprint, url_prefix="/api/post-feedback")

    with app.app_context():
        db.create_all()
    
    return app

def init_server():
    app = create_app()
    cherrypy.tree.graft(app, '/')
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8090,
        'engine.autoreload.on': False
    })

if __name__ == '__main__':
    init_server()
    cherrypy.engine.start()