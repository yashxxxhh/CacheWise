# Smart Caching Layer

## What it does

A backend API that serves data fast by keeping frequently accessed records in memory. Every response tells you whether it came from cache or the database. A background job uses a small ML model to predict popular items and pre-load them before anyone asks.


## How it works

Incoming requests check Redis first. On a hit, data is returned immediately with `"cached": true`. On a miss, the request falls through to SQLite, the result is stored in Redis with a 5-minute TTL, and the response comes back with `"cached": false`. Every fetch is logged. Every 60 seconds, a scheduler reads those logs, runs a RandomForest classifier to predict hot items, and pre-warms the cache — so even first requests to popular items are served from memory.


## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Cache | Redis |
| Database | SQLite |
| Validation | Pydantic |
| ML | scikit-learn (RandomForestClassifier) |
| Scheduler | APScheduler |
| Language | Python 3.10+ |


