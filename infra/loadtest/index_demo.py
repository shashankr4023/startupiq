"""See, with your own eyes, what an index does.

This builds a throwaway 200,000-row table, runs the same query Postgres runs for
"list my newest ideas" (filter by owner, order by created_at, take 20), and
prints the EXPLAIN ANALYZE plan TWICE:

  1. WITHOUT an index -> Postgres does a "Seq Scan": it reads all 200k rows.
  2. WITH a matching index -> Postgres does an "Index Scan": it jumps straight
     to the ~200 matching rows.

Watch the "actual time" and the scan type change. Then the table is dropped, so
nothing in your real schema is touched.

Run from the backend venv (needs asyncpg + dotenv):
    python infra/loadtest/index_demo.py
"""

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROWS = 200_000
OWNERS = 1000  # ~200 rows per owner

QUERY = (
    "EXPLAIN (ANALYZE, BUFFERS) "
    "SELECT * FROM loadtest_demo WHERE owner = $1 ORDER BY created_at DESC LIMIT 20"
)


def _dsn() -> str:
    load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")
    return os.environ["DATABASE_URL_DIRECT"].replace("+asyncpg", "")


async def _explain(conn: asyncpg.Connection, owner) -> None:
    rows = await conn.fetch(QUERY, owner)
    for r in rows:
        print("   " + r[0])


async def main() -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        print(f"Building a throwaway {ROWS:,}-row table…")
        await conn.execute("DROP TABLE IF EXISTS loadtest_demo")
        await conn.execute(
            """
            CREATE TABLE loadtest_demo (
                id          bigint,
                owner       uuid,
                created_at  timestamptz,
                payload     text
            )
            """
        )
        # Fill it server-side with generate_series - one statement, no per-row
        # network round trips. (Contrast with seed_data.py's batched inserts.)
        await conn.execute(
            f"""
            INSERT INTO loadtest_demo
            SELECT g,
                   ('00000000-0000-0000-0000-' || lpad((g % {OWNERS})::text, 12, '0'))::uuid,
                   now() - (g || ' seconds')::interval,
                   'payload row ' || g
            FROM generate_series(1, {ROWS}) AS g
            """
        )
        await conn.execute("ANALYZE loadtest_demo")  # update planner statistics
        owner = await conn.fetchval("SELECT owner FROM loadtest_demo LIMIT 1")

        print("\n=========== WITHOUT INDEX (expect: Seq Scan, reads all rows) ===========")
        await _explain(conn, owner)

        print("\nCreating index on (owner, created_at DESC)…")
        await conn.execute(
            "CREATE INDEX idx_demo_owner_created ON loadtest_demo (owner, created_at DESC)"
        )
        await conn.execute("ANALYZE loadtest_demo")

        print("\n=========== WITH INDEX (expect: Index Scan, jumps to ~200 rows) ===========")
        await _explain(conn, owner)
    finally:
        await conn.execute("DROP TABLE IF EXISTS loadtest_demo")
        await conn.close()
        print("\nThrowaway table dropped. Nothing in your real schema was changed.")


if __name__ == "__main__":
    asyncio.run(main())
