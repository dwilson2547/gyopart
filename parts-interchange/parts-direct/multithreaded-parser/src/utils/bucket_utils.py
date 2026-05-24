import json
import os
from io import BytesIO

from minio import Minio
from .config import Config


class BucketUtils:
    """
    Utility for managing pushing files to a bucket
    """

    def __init__(self, cfg: Config, secure=False):
        self.client = Minio(cfg.bucket_url,
            access_key=cfg.bucket_access,
            secret_key=cfg.bucket_secret,
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
