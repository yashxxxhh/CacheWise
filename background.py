"""
background.py — APScheduler-based background job that pre-caches hot items.

The scheduler runs inside the FastAPI process (no extra worker needed).
Every N minutes it:
  1. Asks predictor.py for the "hot" product / user IDs.
  2. Fetches each from SQLite.
  3. Writes them into Redis with a fresh TTL.

This warms the cache BEFORE users ask for popular items, so the
first request to a hot item still gets a cache HIT.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import db
import cache
import predictor

# How often to run the pre-caching job (seconds).  60 = every minute.
PRECACHE_INTERVAL_SECONDS = 60

# TTL for pre-cached items (slightly longer than the default 300 s
# so they don't expire before the next scheduler run)
PRECACHE_TTL = 400

# Max items to pre-cache per entity type
TOP_N = 5


# ─────────────────────────────────────────────
# The actual pre-caching job
# ─────────────────────────────────────────────

async def precache_hot_items() -> None:
    """Predict and pre-cache hot products + users."""
    print("[Background] Running pre-cache job …")

    for entity, fetch_fn in [("product", db.get_product),
                              ("user",    db.get_user)]:
        hot_ids = predictor.predict_hot_items(entity, top_n=TOP_N)

        cached_count = 0
        for eid in hot_ids:
            # Skip if already fresh in cache
            if cache.cache_exists(entity, eid):
                continue

            data = fetch_fn(eid)
            if data:
                cache.cache_set(entity, eid, data, ttl=PRECACHE_TTL)
                cached_count += 1

        if hot_ids:
            print(f"[Background] Pre-cached {cached_count} new {entity}(s) "
                  f"(hot ids: {hot_ids})")
        else:
            print(f"[Background] No hot {entity}s predicted yet.")

    print("[Background] Pre-cache job complete.")


# ─────────────────────────────────────────────
# Scheduler lifecycle helpers
# ─────────────────────────────────────────────

_scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Register and start the background scheduler."""
    _scheduler.add_job(
        precache_hot_items,
        trigger=IntervalTrigger(seconds=PRECACHE_INTERVAL_SECONDS),
        id="precache_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,   # Don't queue up missed runs
    )
    _scheduler.start()
    print(f"[Background] Scheduler started — "
          f"pre-caching every {PRECACHE_INTERVAL_SECONDS}s.")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler on app shutdown."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Background] Scheduler stopped.")
