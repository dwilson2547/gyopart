import logging
import threading
import time
import queue

q = queue.Queue()

def thread_function(name):
    logging.info("Thread %s: starting", name)
    r = queue.Queue()
    payload = {
        'name': f'thread-{name}',
        'queue': r
    }
    q.put(payload)
    resp = r.get()
    print(resp)
    time.sleep(2)
    logging.info("Thread %s: finishing", name)

def queue_reader():
    while True:
        item = q.get()
        logging.info("queue %s: starting", item['name'])
        time.sleep(2)
        logging.info("queue %s: finishing", item['name'])
        q.task_done()
        item['queue'].put('queue-finished ' + item['name'])

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")

    threading.Thread(target=queue_reader, daemon=True).start()

    threads = list()
    for index in range(3):
        logging.info("Main    : create and start thread %d.", index)
        x = threading.Thread(target=thread_function, args=(index,))
        threads.append(x)
        x.start()

    for index, thread in enumerate(threads):
        logging.info("Main    : before joining thread %d.", index)
        thread.join()
        logging.info("Main    : thread %d done", index)

    q.join()