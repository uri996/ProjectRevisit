import threading
import time
from collections import OrderedDict

from fastapi import HTTPException


class Operations:
    """Bounded, process-local idempotency and mutual exclusion for paid operations.

    Failed requests are not silently retried either. The caller chooses a new request ID
    for a deliberate retry. Services retain their cross-process project file locks.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.busy = set()
        self.seen = OrderedDict()

    def run(self, scope, request_id, action):
        key = (scope, str(request_id))
        with self.lock:
            now = time.monotonic()
            while self.seen and (now - next(iter(self.seen.values())) > 86400):
                self.seen.popitem(last=False)
            if key in self.seen:
                raise HTTPException(409, "该请求已经处理或正在处理，请刷新状态；不要重复发送。")
            if scope in self.busy:
                raise HTTPException(409, "当前项目或设置正在处理其他请求，请等待完成。")
            if len(self.seen) >= 10000:
                raise HTTPException(429, "本次运行的请求过多，请稍后重试。")
            self.seen[key] = now
            self.busy.add(scope)
        try:
            return action()
        finally:
            with self.lock:
                self.busy.remove(scope)
