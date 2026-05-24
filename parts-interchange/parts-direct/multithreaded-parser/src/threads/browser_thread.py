import logging
import queue

from bs4 import BeautifulSoup as bs
from utils.browser_cache import BrowserCache
from utils.browser_util import BrowserUtil
from utils.cached_parser import CachedParser
from utils.constants import ErrorMessages
from utils.queue_request import (InvalidQueueTypeException, QueueRequest,
                                 QueueRequestType)

log = logging.getLogger(__name__)

def browser_queue_thread(browser_queue: queue.Queue, browser_util: BrowserUtil, browser_cache: BrowserCache, cached_parser: CachedParser):
    while True:
        request: QueueRequest = browser_queue.get()

        if request.get_type() == QueueRequestType.get:
            browser_util.navigate(request.payload)
            page_source = browser_util.get_page_source()
            if cached_parser.check_page(page_source):
                browser_cache.add_to_cache(request.payload, page_source)
                request.get_queue().put(page_source)
            else:
                request.get_queue().put(False)
        else:
            log.error(ErrorMessages.InvalidQueueRequestType, 'browser', 'get')

        browser_queue.task_done()
