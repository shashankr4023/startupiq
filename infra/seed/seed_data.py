"""Seed synthetic data so we can test StartupIQ at scale.

Bulk-inserts thousands of ideas (and some jobs) under an EXISTING user, using
batched `executemany` - the right way to insert a lot of rows: one round trip
per batch instead of per row.

Why an existing user? `startup_ideas.user_id` -> `profiles.id` -> `auth.users.id`,
so a brand-new synthetic profile would violate the foreign key. We attach the
seed data to a real account (found by email) and tag every row's title with
"SEED " so it's easy to remove later with --cleanup.

Usage (from the backend venv, so asyncpg/dotenv are available):
    python infra/seed/seed_data.py --email you@example.com --count 10000
    python infra/seed/seed_data.py --email you@example.com --cleanup
"""

import argparse
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

BATCH = 1000
INDUSTRIES = ["SaaS", "Fintech", "Healthtech", "Edtech", "Climate", "AI", "Commerce"]
FEATURES = [
    "competitor_research",
    "target_customer",
    "market_opportunity",
    "risk_identification",
    "mvp_feasibility",
    "revenue_model",
]
JOB_STATUSES = ["completed", "failed", "queued", "running"]


def _dsn() -> str:
    # Use the migration/session-pooler connection (supports plain SQL, IPv4).
    load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")
    url = os.environ["DATABASE_URL_DIRECT"]
    return url.replace("+asyncpg", "")  # asyncpg wants a plain postgresql:// DSN


async def _resolve_user(conn: asyncpg.Connection, email: str | None, user_id: str | None) -> uuid.UUID:
    if user_id:
        return uuid.UUID(user_id)
    row = await conn.fetchrow("SELECT id FROM profiles WHERE email = $1", email)
    if row is None:
        raise SystemExit(f"No profile found for email {email!r}. Sign up / log in once first.")
    return row["id"]


async def seed(count: int, email: str | None, user_id: str | None, job_ratio: int) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        uid = await _resolve_user(conn, email, user_id)
        print(f"Seeding {count} ideas for user {uid} …")

        now = datetime.utcnow()
        idea_ids: list[uuid.UUID] = []
        batch: list[tuple] = []
        for i in range(count):
            iid = uuid.uuid4()
            idea_ids.append(iid)
            # Spread created_at over time so ORDER BY created_at is meaningful.
            created = now - timedelta(minutes=i)
            batch.append(
                (
                    iid, uid, f"SEED idea {i}",
                    "Synthetic startup idea generated for load testing.",
                    random.choice(INDUSTRIES), None, "active", created, created,
                )
            )
            if len(batch) == BATCH:
                await _insert_ideas(conn, batch)
                batch = []
        if batch:
            await _insert_ideas(conn, batch)
        print(f"  inserted {len(idea_ids)} ideas")

        # Seed some jobs too, so the dashboard's GROUP BY has data.
        job_count = count // max(job_ratio, 1)
        jobs: list[tuple] = []
        for _ in range(job_count):
            jobs.append(
                (
                    uuid.uuid4(), uid, random.choice(idea_ids),
                    "run_evaluation", random.choice(FEATURES),
                    random.choice(JOB_STATUSES), 1, None, None, None, None, now, now,
                )
            )
            if len(jobs) == BATCH:
                await _insert_jobs(conn, jobs)
                jobs = []
        if jobs:
            await _insert_jobs(conn, jobs)
        print(f"  inserted {job_count} jobs")
        print("Done.")
    finally:
        await conn.close()


async def _insert_ideas(conn: asyncpg.Connection, rows: list[tuple]) -> None:
    await conn.executemany(
        "INSERT INTO startup_ideas "
        "(id, user_id, title, description, industry, target_market, status, created_at, updated_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        rows,
    )


async def _insert_jobs(conn: asyncpg.Connection, rows: list[tuple]) -> None:
    await conn.executemany(
        "INSERT INTO jobs "
        "(id, user_id, idea_id, job_type, feature_type, status, attempts, "
        " result_json, llm_provider, model_name, error_message, created_at, updated_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
        rows,
    )


async def cleanup(email: str | None, user_id: str | None) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        uid = await _resolve_user(conn, email, user_id)
        # Deleting the SEED ideas cascades to their jobs (FK ON DELETE CASCADE).
        result = await conn.execute(
            "DELETE FROM startup_ideas WHERE user_id = $1 AND title LIKE 'SEED %'", uid
        )
        print(f"Cleanup: {result}")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Seed StartupIQ with synthetic data.")
    p.add_argument("--email", help="email of an existing profile to attach data to")
    p.add_argument("--user-id", help="UUID of an existing profile (alternative to --email)")
    p.add_argument("--count", type=int, default=10000, help="number of ideas to insert")
    p.add_argument("--job-ratio", type=int, default=5, help="1 job per N ideas")
    p.add_argument("--cleanup", action="store_true", help="delete previously seeded rows")
    args = p.parse_args()

    if not args.email and not args.user_id:
        raise SystemExit("Provide --email or --user-id.")

    if args.cleanup:
        asyncio.run(cleanup(args.email, args.user_id))
    else:
        asyncio.run(seed(args.count, args.email, args.user_id, args.job_ratio))


if __name__ == "__main__":
    main()
