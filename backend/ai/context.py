import time
from typing import Optional

# Per-client conversation state (in-memory). For production, swap to Redis.
TTL_SECONDS = 30 * 60

_state: dict = {}


def _now() -> float:
    return time.time()


def _evict_stale():
    cutoff = _now() - TTL_SECONDS
    for k in list(_state.keys()):
        if _state[k]["updated_at"] < cutoff:
            del _state[k]


def get(phone: str) -> dict:
    """Return current conversation state for this client (empty dict if none/expired)."""
    _evict_stale()
    entry = _state.get(phone)
    return entry["data"] if entry else {}


def update(phone: str, **fields) -> dict:
    """Merge new fields into state. Pass value=None to clear a field."""
    _evict_stale()
    entry = _state.setdefault(phone, {"data": {}, "updated_at": _now()})
    for k, v in fields.items():
        if v is None:
            entry["data"].pop(k, None)
        else:
            entry["data"][k] = v
    entry["updated_at"] = _now()
    return entry["data"]


def clear(phone: str):
    _state.pop(phone, None)
