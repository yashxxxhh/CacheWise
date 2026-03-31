"""
models.py — Pydantic data models for request/response validation.
These are NOT SQLAlchemy ORM models; they define the shape of API data.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────
# Product Models
# ─────────────────────────────────────────────

class ProductBase(BaseModel):
    name: str = Field(..., example="Wireless Headphones")
    category: str = Field(..., example="Electronics")
    price: float = Field(..., gt=0, example=49.99)
    stock: int = Field(..., ge=0, example=120)


class ProductCreate(ProductBase):
    """Used when POST /product is called to add a new product."""
    pass


class Product(ProductBase):
    """Full product model returned from the API, including DB id."""
    id: int
    cached: bool = False          # True when served from Redis
    cache_ttl_seconds: Optional[int] = None  # Remaining TTL (if cached)

    class Config:
        from_attributes = True   # Allow ORM-row → model conversion


# ─────────────────────────────────────────────
# User Models
# ─────────────────────────────────────────────

class UserBase(BaseModel):
    name: str = Field(..., example="Priya Sharma")
    email: str = Field(..., example="priya@example.com")
    role: str = Field(default="customer", example="customer")


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    cached: bool = False
    cache_ttl_seconds: Optional[int] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Cache Stats Model
# ─────────────────────────────────────────────

class CacheStats(BaseModel):
    hits: int
    misses: int
    hit_rate_percent: float
    total_requests: int
    cached_keys_count: int


# ─────────────────────────────────────────────
# Generic API Response Wrapper
# ─────────────────────────────────────────────

class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[dict] = None
