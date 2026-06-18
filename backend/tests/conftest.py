"""Shared test fixtures.

These keep tests fast and hermetic (no network, no real Supabase, no real Redis):

1. `get_session` is overridden to use an in-memory SQLite database. We use a
   StaticPool so every session in a test shares the *same* in-memory DB - needed
   when the worker task opens its own session separate from the request's.
2. `get_current_user` is overridden so a test "token" is just a raw user-id
   string - no Supabase JWT / JWKS network call.
3. `get_arq_pool` is overridden with a FakePool that records enqueued jobs
   instead of talking to Redis.
"""

import uuid

import pytest_asyncio
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.core.arq import get_arq_pool
from app.core.cache import InMemoryCache, get_cache
from app.core.security import get_current_user
from app.db.models.profile import Profile
from app.db.session import get_session
from app.main import app

# Rate limiting is disabled across the test suite so functional tests aren't
# affected by request counts. (The limiter itself is exercised manually / in its
# own focused test.)
app.state.limiter.enabled = False


def make_test_engine():
    """In-memory SQLite shared across all connections in the test (StaticPool)."""
    return create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest_asyncio.fixture
async def engine():
    eng = make_test_engine()
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_maker) -> AsyncSession:
    async with session_maker() as s:
        yield s


async def _override_get_current_user(authorization: str = Header(...)) -> uuid.UUID:
    # In tests the bearer "token" is simply the user's UUID string.
    token = authorization.split(" ", 1)[1]
    return uuid.UUID(token)


class FakePool:
    """Stand-in for the Arq Redis pool: records enqueued jobs, never hits Redis."""

    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, function: str, *args, **kwargs):
        self.enqueued.append((function, args, kwargs))
        return None


@pytest_asyncio.fixture
async def fake_pool():
    pool = FakePool()
    app.dependency_overrides[get_arq_pool] = lambda: pool
    yield pool
    app.dependency_overrides.pop(get_arq_pool, None)


@pytest_asyncio.fixture
async def cache() -> InMemoryCache:
    return InMemoryCache()


@pytest_asyncio.fixture
async def client(session_maker, cache):
    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_cache] = lambda: cache
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def auth_header(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


@pytest_asyncio.fixture
async def user_id(session: AsyncSession) -> uuid.UUID:
    uid = uuid.uuid4()
    session.add(Profile(id=uid, email=f"{uid}@example.com"))
    await session.commit()
    return uid
