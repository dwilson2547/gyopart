import logging
import os
import queue
import time
import urllib.request

from utils.bucket_utils import BucketUtils
from utils.config import Config
from utils.constants import BUCKET_NAME, ErrorMessages
from utils.queue_request import (InvalidQueueTypeException, QueueRequest,
                                 QueueRequestType)

log = logging.getLogger(__name__)

def images_queue_thread(image_queue: queue.Queue, images, cfg: Config, bucket_utils: BucketUtils):
    while True:
        request: QueueRequest = image_queue.get()

        if request.get_type() == QueueRequestType.get:
            if request.payload in images:
                request.get_queue().put(images[request.payload])
            else:
                request.get_queue().put(False)
            image_queue.task_done()
        elif request.get_type() == QueueRequestType.put:
            if file_name not in images:
                url = request.payload['url']
                file_name = request.payload['file_name']
                alt_text = request.payload['alt']
                saved, uploaded = save_image(url, file_name, cfg, bucket_utils)
                images[file_name] = {
                    'url': url,
                    'alt': alt_text,
                    'saved': saved,
                    'uploaded': uploaded
                }
            request.get_queue().put(True)
            image_queue.task_done()
        elif request.get_type() == QueueRequestType.done:
            request.get_queue().put(images)
            image_queue.task_done()
        else:
            log.error(ErrorMessages.InvalidQueueRequestType, 'image', 'get, put, done')
            raise InvalidQueueTypeException()


def save_image(url, file_name, cfg: Config, bucket_utils: BucketUtils):
    file_path = os.path.join(cfg.IMG_DIR, file_name)

    print(f'Saving image: {file_name}')

    # Check to see if the image is already downloaded, had some data loss at some point and this helps to rebuild
    if os.path.exists(file_path):
        print('Image already downloaded')
    else:
        time.sleep(3)
        try:
            urllib.request.urlretrieve(url, file_path)
        except:
            log.error('Failed to save image at url: %s', url)
            return False, False

    try:
        bucket_utils.upload_image_to_bucket(BUCKET_NAME, cfg.config_name, file_name, file_path)
    except Exception as ex:
        log.error('Failed to upload image to bucket: %s', ex)
        return True, False

    return True, True