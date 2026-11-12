"""Cache em memoria com TTL, compartilhado por todos os modulos."""
import threading
import time

from config import CFG

_cache = {}
_cache_lock = threading.Lock()


def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
    if item and item[0] > time.time():
        return item[1]
    return None


def cache_set(key, value, minutes=None):
    ttl = (minutes if minutes is not None else CFG["cache_minutes"]) * 60
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)
