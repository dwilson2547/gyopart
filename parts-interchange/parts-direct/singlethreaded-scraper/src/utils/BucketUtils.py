import json
import os
from io import BytesIO

from minio import Minio


class BucketUtils:

    def __init__(self, url=None, access=None, secret=None, secure=False):
        if not url:
            url = os.getenv('BUCKET_URL')
            url = url if url else None
        if not access:
            access = os.getenv('BUCKET_ACCESS')
            access = access if access else None
        if not secret:
            secret = os.getenv('BUCKET_SECRET')
            secret = secret if secret else None

        self.client = Minio(url,
            access_key=access,
            secret_key=secret,
            secure=secure)

        print(self.client.list_buckets())
        print('BucketUtils Init Successful')

    def upload_image_to_bucket(self, bucket: str, make: str, file_name: str, file_path: str):
        dest_path = f'{make}/images/{file_name}'
        self.client.fput_object(bucket, dest_path, file_path)

    def dump_json_to_bucket(self, bucket: str, make: str, file_name: str, data: dict):
        str_data = json.dumps(data).encode("utf-8")
        dest_path = f'{make}/{file_name}'
        self.client.put_object(bucket, dest_path, data=BytesIO(str_data), length=len(str_data))
