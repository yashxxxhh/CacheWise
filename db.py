"""
db.py — SQLite database connection, schema creation, and query helpers.

We use Python's built-in `sqlite3` module (zero install needed).
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = "smart_cache.db"

# Connect and list tables
conn = sqlite3.connect(DB_PATH)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables in DB:", tables)
conn.close()

# ─────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows accessible as row["column"]
    return conn


# ─────────────────────────────────────────────
# Schema bootstrap  (called once at startup)
# ─────────────────────────────────────────────

def init_db() -> None:
    """Create tables if they don't exist yet."""
    conn = get_connection()
    cur = conn.cursor()

    # Products table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            category TEXT    NOT NULL,
            price    REAL    NOT NULL,
            stock    INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role  TEXT NOT NULL DEFAULT 'customer'
        )
    """)

    # Access-log table — used by the AI predictor to find "hot" items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            entity     TEXT    NOT NULL,   -- 'product' or 'user'
            entity_id  INTEGER NOT NULL,
            accessed_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Schema ready.")


# ─────────────────────────────────────────────
# Seed sample data (idempotent — skips if already present)
# ─────────────────────────────────────────────

SAMPLE_PRODUCTS = [
    ("Wireless Headphones",    "Electronics",   49.99,  120),
    ("Mechanical Keyboard",    "Electronics",   89.99,   75),
    ("Ergonomic Mouse",        "Electronics",   34.99,  200),
    ("USB-C Hub 7-in-1",       "Electronics",   29.99,  340),
    ("4K Webcam",              "Electronics",   79.99,   60),
    ("Running Shoes Pro",      "Sports",        59.99,   90),
    ("Yoga Mat Extra Thick",   "Sports",        24.99,  150),
    ("Resistance Bands Set",   "Sports",        14.99,  300),
    ("Stainless Water Bottle", "Kitchen",       18.99,  500),
    ("Air Fryer 5L",           "Kitchen",       89.99,   40),
    ("Coffee Grinder Manual",  "Kitchen",       22.99,   80),
    ("Desk Lamp LED",          "Office",        32.99,  110),
    ("Monitor Stand Bamboo",   "Office",        44.99,   55),
    ("Cable Management Box",   "Office",         9.99,  220),
    ("Notebook Dotted A5",     "Stationery",     7.99,  600),
]

SAMPLE_USERS = [
    ("Priya Sharma",   "priya@example.com",   "customer"),
    ("Arjun Mehta",    "arjun@example.com",   "customer"),
    ("Kavya Nair",     "kavya@example.com",   "admin"),
    ("Rohan Das",      "rohan@example.com",   "customer"),
    ("Sneha Patel",    "sneha@example.com",   "customer"),
    ("Vikram Singh",   "vikram@example.com",  "manager"),
    ("Ananya Rao",     "ananya@example.com",  "customer"),
    ("Dev Kumar",      "dev@example.com",     "customer"),
]


def seed_data() -> None:
    """Insert sample data if tables are empty."""
    conn = get_connection()
    cur = conn.cursor()

    # Products
    count = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)",
            SAMPLE_PRODUCTS
        )
        print(f"[DB] Seeded {len(SAMPLE_PRODUCTS)} sample products.")

    # Users
    count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO users (name, email, role) VALUES (?,?,?)",
            SAMPLE_USERS
        )
        print(f"[DB] Seeded {len(SAMPLE_USERS)} sample users.")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Product queries
# ─────────────────────────────────────────────

def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_products() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_product(name: str, category: str, price: float, stock: int) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)",
        (name, category, price, stock)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_product(new_id)


# ─────────────────────────────────────────────
# User queries
# ─────────────────────────────────────────────

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(name: str, email: str, role: str) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (name, email, role) VALUES (?,?,?)",
        (name, email, role)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return get_user(new_id)


# ─────────────────────────────────────────────
# Access-log helpers (used by predictor.py)
# ─────────────────────────────────────────────

def log_access(entity: str, entity_id: int) -> None:
    """Record that `entity_id` of type `entity` was accessed."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO access_log (entity, entity_id) VALUES (?, ?)",
        (entity, entity_id)
    )
    conn.commit()
    conn.close()


def get_access_counts(entity: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Return access counts per entity_id, sorted by frequency (descending)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT entity_id, COUNT(*) as access_count
        FROM access_log
        WHERE entity = ?
        GROUP BY entity_id
        ORDER BY access_count DESC
        LIMIT ?
    """, (entity, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
