from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class TTLCache:
    def __init__(self, ttl_seconds: float, maxsize: int = 512):
        self.ttl_seconds = ttl_seconds
        self.maxsize = maxsize
        self._lock = threading.Lock()
        self._data: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: Hashable, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._data) >= self.maxsize:
                expired = [k for k, (expires_at, _) in self._data.items() if expires_at <= now]
                for k in expired:
                    self._data.pop(k, None)
                while len(self._data) >= self.maxsize:
                    self._data.pop(next(iter(self._data)))
            self._data[key] = (now + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
