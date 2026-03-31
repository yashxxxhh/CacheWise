"""
cache.py — Redis caching layer with get/set/delete, TTL, and hit/miss stats.

Redis is used as an in-memory key-value store.
All values are JSON-serialised before storing and deserialised on retrieval.

Stats are stored in Redis itself under the key  "cache:stats"
so they survive process restarts (as long as Redis is running).
"""

import json
import redis
from typing import Any, Optional, Dict

# ─────────────────────────────────────────────
# Redis client (local, no auth required)
# ─────────────────────────────────────────────

# Change host/port if your Redis runs elsewhere
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB   = 0

# Default cache TTL in seconds (5 minutes)
DEFAULT_TTL = 300

# Redis key used to count hits / misses
STATS_KEY = "cache:stats"

try:
    _redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,   # Return str, not bytes
        socket_connect_timeout=2,
    )
    _redis_client.ping()         # Fail fast if Redis is not running
    REDIS_AVAILABLE = True
    print("[Cache] Redis connected ✓")
except (redis.ConnectionError, redis.TimeoutError) as exc:
    _redis_client = None
    REDIS_AVAILABLE = False
    print(f"[Cache] WARNING: Redis not available ({exc}). "
          "All requests will hit the database.")


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _increment_stat(field: str) -> None:
    """Atomically increment hits or misses counter in Redis."""
    if REDIS_AVAILABLE:
        _redis_client.hincrby(STATS_KEY, field, 1)


def _build_key(entity: str, entity_id: Any) -> str:
    """e.g.  product:42  or  user:7  or  products:all"""
    return f"{entity}:{entity_id}"


# ─────────────────────────────────────────────
# Public cache API
# ─────────────────────────────────────────────

def cache_get(entity: str, entity_id: Any) -> Optional[Dict]:
    """
    Try to fetch data from Redis.
    Returns (data_dict, ttl_seconds) on HIT, or (None, None) on MISS.
    """
    if not REDIS_AVAILABLE:
        _increment_stat("misses")
        return None, None

    key = _build_key(entity, entity_id)
    raw = _redis_client.get(key)

    if raw is None:
        _increment_stat("misses")
        return None, None

    # Cache HIT — also return remaining TTL so the API can expose it
    ttl = _redis_client.ttl(key)   # seconds; -1 = no expiry; -2 = gone
    _increment_stat("hits")
    return json.loads(raw), ttl


def cache_set(entity: str, entity_id: Any, data: Dict, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store data in Redis under key  entity:entity_id  with the given TTL.
    Returns True on success, False if Redis is unavailable.
    """
    if not REDIS_AVAILABLE:
        return False

    key = _build_key(entity, entity_id)
    _redis_client.setex(key, ttl, json.dumps(data))
    return True


def cache_delete(entity: str, entity_id: Any) -> bool:
    """Remove a single key from Redis (call after update/delete operations)."""
    if not REDIS_AVAILABLE:
        return False

    key = _build_key(entity, entity_id)
    _redis_client.delete(key)
    return True


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a glob pattern, e.g. 'product:*'.
    Returns the number of keys deleted.
    """
    if not REDIS_AVAILABLE:
        return 0

    keys = _redis_client.keys(pattern)
    if keys:
        return _redis_client.delete(*keys)
    return 0


def cache_exists(entity: str, entity_id: Any) -> bool:
    """Return True if the key currently exists in Redis."""
    if not REDIS_AVAILABLE:
        return False
    return bool(_redis_client.exists(_build_key(entity, entity_id)))


# ─────────────────────────────────────────────
# Cache statistics
# ─────────────────────────────────────────────

def get_cache_stats() -> Dict[str, Any]:
    """
    Return a dict with:
      hits, misses, hit_rate_percent, total_requests, cached_keys_count
    """
    if not REDIS_AVAILABLE:
        return {
            "hits": 0,
            "misses": 0,
            "hit_rate_percent": 0.0,
            "total_requests": 0,
            "cached_keys_count": 0,
            "redis_available": False,
        }

    raw_stats = _redis_client.hgetall(STATS_KEY)
    hits   = int(raw_stats.get("hits",   0))
    misses = int(raw_stats.get("misses", 0))
    total  = hits + misses
    rate   = round((hits / total * 100), 2) if total > 0 else 0.0

    # Count ALL data keys (exclude the stats key itself)
    all_keys = _redis_client.keys("*")
    data_keys = [k for k in all_keys if k != STATS_KEY]

    return {
        "hits": hits,
        "misses": misses,
        "hit_rate_percent": rate,
        "total_requests": total,
        "cached_keys_count": len(data_keys),
        "redis_available": True,
    }


def reset_cache_stats() -> None:
    """Zero-out the hit/miss counters (useful for benchmarking)."""
    if REDIS_AVAILABLE:
        _redis_client.delete(STATS_KEY)


def flush_all_cache() -> None:
    """Wipe ALL keys in the current Redis DB. Use with care."""
    if REDIS_AVAILABLE:
        _redis_client.flushdb()
        print("[Cache] All keys flushed.")
