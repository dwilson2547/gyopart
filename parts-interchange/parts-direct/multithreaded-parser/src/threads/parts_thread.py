import logging
import queue

from utils.queue_request import (InvalidQueueTypeException, QueueRequest,
                                 QueueRequestType)

log = logging.getLogger(__name__)

def parts_queue_thread(part_queue: queue.Queue, parts):
    while True:
        request: QueueRequest = part_queue.get()

        if request.get_type() == QueueRequestType.get:
            if request.payload in parts:
                request.get_queue().put(parts[request.payload])
            else:
                request.get_queue().put(False)
            part_queue.task_done()
        elif request.get_type() == QueueRequestType.put:
            part_number = request.payload['part_number']
            if part_number not in parts:
                parts[part_number] = request.payload
            request.get_queue().put(True)
            part_queue.task_done()
        elif request.get_type() == QueueRequestType.done:
            request.get_queue().put(parts)
            part_queue.task_done()
        else:
            log.error('Improper message passed to parts queue, only expect message types get or put')
            raise InvalidQueueTypeException()
