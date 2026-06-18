from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.arq import create_arq_pool
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open shared Redis-backed resources once on startup, reuse for all requests.
    app.state.arq_pool = await create_arq_pool()       # job queue (Phase 3)
    app.state.cache_redis = Redis.from_url(settings.REDIS_URL)
    app.state.cache = RedisCache(app.state.cache_redis)  # cache (Phase 4)
    yield
    await app.state.arq_pool.aclose()
    await app.state.cache_redis.aclose()


app = FastAPI(title="StartupIQ API", version="0.1.0", lifespan=lifespan)

# Register the rate limiter: attach it to the app and install the handler that
# turns an exceeded limit into a clean 429 Too Many Requests response.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
