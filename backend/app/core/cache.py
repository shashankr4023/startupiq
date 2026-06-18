"""A tiny caching layer over Redis.

A *cache* stores the result of expensive work (a DB query, an aggregation) so a
repeat request can be served instantly from fast memory instead of recomputing.
Two rules govern a cache:

- **TTL (time-to-live):** every cached value expires after N seconds, so it can
  never be *too* stale.
- **Invalidation:** when the underlying data changes (a write), delete the
  cached copy so the next read recomputes fresh.

We program against the `Cache` interface (not Redis directly) - the same
abstraction trick from Chapter 6 - so tests can swap in an in-memory fake.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from fastapi import Request
from redis.asyncio import Redis


class Cache(ABC):
    @abstractmethod
    async def get_json(self, key: str) -> Any | None:
        """Return the cached value for `key`, or None on a miss."""

    @abstractmethod
    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store `value` under `key`, expiring after `ttl_seconds`."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove `key` (used to invalidate after a write)."""


class RedisCache(Cache):
    """Production cache backed by Redis."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get_json(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)


class InMemoryCache(Cache):
    """A simple dict-backed cache used in tests (no Redis, TTL ignored)."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any | None:
        return self._store.get(key)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


def get_cache(request: Request) -> Cache:
    """FastAPI dependency: the cache created at app startup (see app/main.py
    lifespan). Tests override this with an InMemoryCache."""
    return request.app.state.cache
