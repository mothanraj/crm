"""In-process live-update signalling for the website.

Single-worker safe: a monotonic seq + timestamp. SSE endpoint polls this
every second and emits an event when seq changes. Multi-worker setups
should replace with Redis pubsub later — API (bump/subscribe_state) stays.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_state = {"seq": 0, "updated_at": datetime.now(timezone.utc).isoformat()}


def bump() -> int:
    with _lock:
        _state["seq"] += 1
        _state["updated_at"] = datetime.now(timezone.utc).isoformat()
        return _state["seq"]


def state() -> dict:
    with _lock:
        return dict(_state)
