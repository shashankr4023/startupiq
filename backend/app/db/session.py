from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# DATABASE_URL points at Supabase's transaction-mode pooler (Supavisor/pgbouncer,
# port 6543). That pooler hands each transaction a possibly-different backend
# connection, which is incompatible with asyncpg's default prepared-statement
# caching - you get "prepared statement __asyncpg_stmt_N__ already exists".
# The fix: disable both caches and give any prepared statements unique names.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={
        "statement_cache_size": 0,           # asyncpg's own cache off
        "prepared_statement_cache_size": 0,  # SQLAlchemy dialect cache off
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    },
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
