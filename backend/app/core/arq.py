"""Shared Redis/Arq connection helpers.

Both sides of the queue use these:
- the API (producer) creates a pool to *enqueue* jobs
- the worker (consumer) uses the same RedisSettings to *pull* jobs

Keeping the connection settings in one place means the producer and consumer
can never drift out of sync.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

from app.core.config import settings


def get_redis_settings() -> RedisSettings:
    """Parse REDIS_URL (e.g. redis://localhost:6379) into Arq's settings object."""
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def create_arq_pool() -> ArqRedis:
    """Open a connection pool used by the API to enqueue jobs."""
    return await create_pool(get_redis_settings())


def get_arq_pool(request: Request) -> ArqRedis:
    """FastAPI dependency: hand endpoints the pool created at app startup
    (see the lifespan in app/main.py). Tests override this with a fake pool."""
    return request.app.state.arq_pool
