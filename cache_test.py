import sqlite3
import redis
import time
from pathlib import Path


r = redis.Redis(host='localhost', port=6379, db=0)

# Only flush if Redis is completely empty
if len(r.keys()) == 0:
    print("Redis empty, first run: clearing (optional)")
    r.flushdb()
else:
    print("Redis already has data, keeping cache")

# --- DB path ---
db_path = Path(__file__).parent / "smart_cache.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# --- Tables to test ---
tables_to_test = ['users', 'products', 'access_log']  # Add more if needed

# --- Function with Redis cache ---
def fetch_row_with_cache(table, row_id):
    key = f"{table}:{row_id}"
    cached = r.get(key)
    if cached:
        return cached.decode(), True  # From Redis
    cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    if row:
        r.set(key, str(row))
    return row, False  # From DB

# --- Full DB tracking ---
total_db_time_all = 0
total_cache_time_all = 0
total_rows_all = 0

# --- Test each table ---
for table in tables_to_test:
    print(f"Testing table: {table}")
    cursor.execute(f"SELECT id FROM {table}")
    row_ids = [row[0] for row in cursor.fetchall()]
    
    if not row_ids:
        print(f"  Table {table} is empty, skipping\n")
        continue

    total_db_time = 0
    total_cache_time = 0

    for row_id in row_ids:
        # DB fetch
        start = time.time()
        fetch_row_with_cache(table, row_id)
        db_time = (time.time() - start) * 1000
        total_db_time += db_time

        # Cache fetch
        start = time.time()
        fetch_row_with_cache(table, row_id)
        cache_time = (time.time() - start) * 1000
        total_cache_time += cache_time

    avg_db = total_db_time / len(row_ids)
    avg_cache = total_cache_time / len(row_ids)
    improvement = ((avg_db - avg_cache) / avg_db) * 100

    print(f"  Rows tested: {len(row_ids)}")
    print(f"  Avg DB fetch time: {avg_db:.3f} ms")
    print(f"  Avg Redis fetch time: {avg_cache:.3f} ms")
    print(f"  Table improvement: {improvement:.2f}%\n")

    # Add to full DB totals
    total_db_time_all += total_db_time
    total_cache_time_all += total_cache_time
    total_rows_all += len(row_ids)

# --- Full DB averages ---
if total_rows_all > 0:
    avg_db_all = total_db_time_all / total_rows_all
    avg_cache_all = total_cache_time_all / total_rows_all
    overall_improvement = ((avg_db_all - avg_cache_all) / avg_db_all) * 100
    print("Overall DB performance:")
    print(f"  Total rows tested: {total_rows_all}")
    print(f"  Avg DB fetch time: {avg_db_all:.3f} ms")
    print(f"  Avg Redis fetch time: {avg_cache_all:.3f} ms")
    print(f"  Overall improvement: {overall_improvement:.2f}%")
else:
    print("No rows found in DB to test.")

conn.close()
print("Full cache latency test complete")