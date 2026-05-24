import queue
from enum import Enum


class QueueRequestType(Enum):
    get = 'get'
    put = 'put'
    check = 'check'
    done = 'done'

class QueueRequest:
    request_type: QueueRequestType
    payload: dict
    response_queue: queue.Queue

    def __init__(self, request_type: QueueRequestType, payload: dict):
        self.request_type = request_type
        self.payload = payload
        self.response_queue = queue.Queue()

    def get_queue(self):
        return self.response_queue
    
    def get_type(self):
        return self.request_type
    
class InvalidQueueTypeException(Exception):
    pass