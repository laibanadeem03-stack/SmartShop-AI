"""Bounded process-local TTL cache. Never retain full catalog signal vectors."""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import threading
import time
from uuid import uuid4

from ..errors import ApiError


@dataclass(frozen=True)
class Batch:
    private_user: str | None
    model: str
    seen: frozenset
    results: tuple
    sources: tuple
    traces: tuple


class BatchCache:
    def __init__(self, capacity=100, ttl=300, clock=time.monotonic):
        if not 1 <= capacity <= 100 or not 0 < ttl <= 300:
            raise ValueError('Invalid bounded cache settings')
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.entries, self.lock = OrderedDict(), threading.Lock()

    def _expire(self, now):
        for key in [key for key,(expires,_) in self.entries.items() if expires <= now]:
            del self.entries[key]

    def put(self, batch):
        with self.lock:
            now = self.clock()
            self._expire(now)
            while len(self.entries) >= self.capacity:
                self.entries.popitem(last=False)
            key = uuid4().hex
            self.entries[key] = (now+self.ttl, deepcopy(batch))
            return key

    def get(self, key):
        with self.lock:
            self._expire(self.clock())
            value = self.entries.get(key)
            if value is None:
                raise ApiError(404, 'BATCH_NOT_FOUND', 'Recommendation batch is unavailable or expired.')
            return deepcopy(value[1])

    def clear(self):
        with self.lock:
            self.entries.clear()
