"""
main.py — FastAPI application entry point.

Start the server:
    uvicorn main:app --reload --port 8000

Interactive docs:
    http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

import db
import cache
import background
from models import (
    Product, ProductCreate,
    User, UserCreate,
    CacheStats, APIResponse,
)


# ─────────────────────────────────────────────
# App lifecycle
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup / shutdown logic."""
    # ── Startup ──
    db.init_db()          # Create SQLite tables
    db.seed_data()        # Insert sample data if empty
    background.start_scheduler()   # Begin pre-caching hot items
    yield
    # ── Shutdown ──
    background.stop_scheduler()


app = FastAPI(
    title="Smart Caching Layer API",
    description=(
        "FastAPI + Redis + SQLite demo showing cache hits/misses, "
        "TTL management, cache statistics, and AI-based pre-caching."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# Root
# ─────────────────────────────────────────────

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Smart Caching Layer is running ",
        "docs": "/docs",
        "redis": cache.REDIS_AVAILABLE,
    }


# ═════════════════════════════════════════════
# PRODUCT endpoints
# ═════════════════════════════════════════════

@app.get("/product/{product_id}", response_model=Product, tags=["Products"])
def get_product(product_id: int):
    """
    Fetch a single product by ID.
    - First checks Redis cache (sets `cached: true` if found).
    - Falls back to SQLite; then stores result in Redis for next request.
    - Logs the access so the AI predictor can learn hot items.
    """
    # ── 1. Check cache ──
    data, ttl = cache.cache_get("product", product_id)
    if data:
        data["cached"] = True
        data["cache_ttl_seconds"] = ttl
        return data

    # ── 2. Cache miss → hit database ──
    data = db.get_product(product_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found."
        )

    # ── 3. Populate cache for next request ──
    cache.cache_set("product", product_id, data)

    # ── 4. Log access for the AI predictor ──
    db.log_access("product", product_id)

    data["cached"] = False
    data["cache_ttl_seconds"] = None
    return data


@app.get("/products", tags=["Products"])
def get_all_products():
    """
    Fetch all products.
    The entire product list is cached as a single Redis key `products:all`.
    """
    data, ttl = cache.cache_get("products", "all")
    if data:
        return {"cached": True, "cache_ttl_seconds": ttl, "products": data}

    products = db.get_all_products()
    cache.cache_set("products", "all", products, ttl=120)   # shorter TTL for lists

    return {"cached": False, "cache_ttl_seconds": None, "products": products}


@app.post("/product", response_model=Product, status_code=status.HTTP_201_CREATED, tags=["Products"])
def create_product(body: ProductCreate):
    """
    Add a new product to SQLite.
    Also invalidates the `products:all` cache key so the list stays fresh.
    """
    new_product = db.create_product(
        name=body.name,
        category=body.category,
        price=body.price,
        stock=body.stock,
    )
    # Invalidate stale list cache
    cache.cache_delete("products", "all")

    new_product["cached"] = False
    new_product["cache_ttl_seconds"] = None
    return new_product


@app.delete("/product/{product_id}", tags=["Products"])
def delete_product_cache(product_id: int):
    """
    Manually evict a product from Redis (useful for testing cache misses).
    Does NOT delete the product from SQLite.
    """
    deleted = cache.cache_delete("product", product_id)
    cache.cache_delete("products", "all")
    return {"evicted": deleted, "product_id": product_id}


# ═════════════════════════════════════════════
# USER endpoints
# ═════════════════════════════════════════════

@app.get("/user/{user_id}", response_model=User, tags=["Users"])
def get_user(user_id: int):
    """
    Fetch a single user by ID — same cache-aside pattern as products.
    """
    data, ttl = cache.cache_get("user", user_id)
    if data:
        data["cached"] = True
        data["cache_ttl_seconds"] = ttl
        return data

    data = db.get_user(user_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found."
        )

    cache.cache_set("user", user_id, data)
    db.log_access("user", user_id)

    data["cached"] = False
    data["cache_ttl_seconds"] = None
    return data


@app.get("/users", tags=["Users"])
def get_all_users():
    """Fetch all users with caching."""
    data, ttl = cache.cache_get("users", "all")
    if data:
        return {"cached": True, "cache_ttl_seconds": ttl, "users": data}

    users = db.get_all_users()
    cache.cache_set("users", "all", users, ttl=120)

    return {"cached": False, "cache_ttl_seconds": None, "users": users}


@app.post("/user", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
def create_user(body: UserCreate):
    """Add a new user and invalidate the user-list cache."""
    new_user = db.create_user(name=body.name, email=body.email, role=body.role)
    cache.cache_delete("users", "all")
    new_user["cached"] = False
    new_user["cache_ttl_seconds"] = None
    return new_user


# ═════════════════════════════════════════════
# CACHE management endpoints
# ═════════════════════════════════════════════

@app.get("/cache/stats", response_model=CacheStats, tags=["Cache"])
def get_cache_stats():
    """
    Returns cumulative cache hit / miss statistics stored in Redis.
    Hit rate rises as clients repeatedly request the same items.
    """
    stats = cache.get_cache_stats()
    return stats


@app.post("/cache/flush", tags=["Cache"])
def flush_cache():
    """Wipe all Redis keys (useful for benchmarking from a clean state)."""
    cache.flush_all_cache()
    cache.reset_cache_stats()
    return {"message": "Cache flushed. All subsequent requests will hit SQLite."}


@app.post("/cache/reset-stats", tags=["Cache"])
def reset_stats():
    """Zero-out hit/miss counters without flushing cached data."""
    cache.reset_cache_stats()
    return {"message": "Cache statistics reset to zero."}


@app.post("/cache/precache-now", tags=["Cache"])
async def trigger_precache():
    """
    Manually trigger the AI pre-caching job right now
    (normally runs on the background scheduler every 60 s).
    """
    await background.precache_hot_items()
    return {"message": "Pre-caching job executed. Check /cache/stats for updated counts."}
