"""
predictor.py — Lightweight ML model to predict "hot" items worth pre-caching.

Algorithm
─────────
We train a simple scikit-learn model on access-log data:
  Features: [entity_id, access_count, recency_score]
  Label:    is_hot  (1 if access_count > threshold, else 0)

On first run there's little access data, so we fall back to returning
all items (everything is worth caching when the log is sparse).

The model is retrained every time pre-caching runs (lightweight enough
that this only takes milliseconds for a small SQLite dataset).
"""

import math
from typing import List, Tuple

# scikit-learn is optional — gracefully degrade if not installed
try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("[Predictor] scikit-learn / numpy not found. "
          "Falling back to frequency-based heuristic.")

import db  # local module


# ─────────────────────────────────────────────
# Feature engineering
# ─────────────────────────────────────────────

def _build_features(access_records: List[dict]) -> List[Tuple]:
    """
    Convert raw access counts into feature rows:
      (entity_id, access_count, log_access_count)
    log-scaling smooths outliers.
    """
    rows = []
    for r in access_records:
        eid   = r["entity_id"]
        count = r["access_count"]
        log_c = math.log1p(count)   # log(1 + count) — never 0
        rows.append((eid, count, log_c))
    return rows


# ─────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────

HOT_THRESHOLD = 3   # Items accessed ≥ this many times are "hot"


def predict_hot_items(entity: str, top_n: int = 5) -> List[int]:
    """
    Return a list of entity_ids predicted to be "hot" (high access frequency).

    entity: 'product' or 'user'
    top_n:  maximum number of hot ids to return

    Strategy
    ────────
    1. Fetch access counts from the DB.
    2. If ML is available and we have enough samples → train RandomForest.
    3. Otherwise → simple frequency sort (top-N by count).
    """
    records = db.get_access_counts(entity, limit=100)

    if not records:
        # No access log yet — return empty; background.py will skip pre-caching
        print(f"[Predictor] No access data for '{entity}' yet.")
        return []

    # ── Frequency-only fallback ──────────────────────────────────────────
    if not ML_AVAILABLE or len(records) < 5:
        hot = sorted(records, key=lambda r: r["access_count"], reverse=True)
        ids = [r["entity_id"] for r in hot[:top_n]]
        print(f"[Predictor] Frequency heuristic → hot {entity} ids: {ids}")
        return ids

    # ── ML-based prediction ──────────────────────────────────────────────
    features = _build_features(records)
    X = np.array([[f[0], f[1], f[2]] for f in features])
    y = np.array([1 if f[1] >= HOT_THRESHOLD else 0 for f in features])

    # Need at least one sample from each class to train a classifier
    if len(set(y)) < 2:
        # All items below threshold — just return top-N by frequency
        ids = [r["entity_id"] for r in records[:top_n]]
        return ids

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_scaled, y)

    proba = clf.predict_proba(X_scaled)[:, 1]   # probability of class=1 (hot)

    # Pair each record with its predicted hot-probability and sort
    scored = sorted(
        zip(records, proba),
        key=lambda pair: pair[1],
        reverse=True
    )

    hot_ids = [rec["entity_id"] for rec, prob in scored if prob > 0.5][:top_n]
    print(f"[Predictor] ML model → hot {entity} ids: {hot_ids}")
    return hot_ids
