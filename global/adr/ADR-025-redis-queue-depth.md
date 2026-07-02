# ADR-025: Redis Queue Depth for Celery Monitoring

**Date:** 2026-07-02
**Status:** Accepted

## Context
The admin dashboard requires real-time visibility into Celery queue depths (`sync`, `attune`, `whisper`). Celery uses Redis as its broker, storing queue state as Redis lists. Querying the PostgreSQL database would yield stale or incorrect data since queue state lives in Redis, not the application database.

## Decision
Read queue depths directly from Redis using `redis-py` (`llen()` on each queue key). Cache results with a 5-second TTL per queue to avoid thrashing Redis on page load.

## Consequences
- **Positive:** Accurate, real-time queue visibility. Minimal overhead (single `llen()` per queue per 5s). No stale data from DB polling.
- **Negative:** Tight coupling to Redis implementation. If broker changes (e.g., RabbitMQ), implementation must be updated.
- **Neutral:** Redis is a hard dependency for Celery in current architecture, so no new dependency introduced.

## Compliance
Queue depth views must use a cached helper (e.g., `RedisQueueInspector.get_depth(queue_name)`) with 5-second TTL. Direct database queries for queue depth are prohibited. The cache key should include the queue name to avoid cross-contamination.

## Implementation Pattern
```python
class RedisQueueInspector:
    def __init__(self, redis_client, ttl=5):
        self.redis = redis_client
        self.ttl = ttl
        self._cache = {}

    def get_depth(self, queue_name: str) -> int:
        cache_key = f"queue_depth:{queue_name}"
        if cache_key in self._cache:
            cached_time, cached_value = self._cache[cache_key]
            if time.time() - cached_time < self.ttl:
                return cached_value
        depth = self.redis.llen(queue_name)
        self._cache[cache_key] = (time.time(), depth)
        return depth
```

## Related
- ADR-023: Celery Schedule Configuration (Celery Beat usage)
