"""Usage dashboard - aggregate stats for the current user.

This endpoint is the textbook case for *time-based* caching. The counts are
expensive (they scan/aggregate rows) but don't need to be perfectly up to the
millisecond, so we cache the whole result for a short TTL. There's no explicit
invalidation here - the data simply refreshes when the TTL expires.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.cache import Cache, get_cache
from app.core.config import settings
from app.core.security import get_current_user
from app.db.models.idea import StartupIdea
from app.db.models.job import Job
from app.db.session import AsyncSession, get_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    cache: Cache = Depends(get_cache),
) -> dict:
    key = f"dashboard:{user_id}"

    cached = await cache.get_json(key)
    if cached is not None:
        return cached

    # Total ideas for this user.
    ideas_total = await session.scalar(
        select(func.count()).select_from(StartupIdea).where(StartupIdea.user_id == user_id)
    )

    # Ideas grouped by status (active / archived / ...).
    idea_status_rows = await session.execute(
        select(StartupIdea.status, func.count())
        .where(StartupIdea.user_id == user_id)
        .group_by(StartupIdea.status)
    )
    ideas_by_status = {status: count for status, count in idea_status_rows.all()}

    # Evaluation jobs grouped by status (queued / running / completed / failed).
    job_status_rows = await session.execute(
        select(Job.status, func.count())
        .where(Job.user_id == user_id)
        .group_by(Job.status)
    )
    jobs_by_status = {status: count for status, count in job_status_rows.all()}

    data = {
        "ideas_total": ideas_total or 0,
        "ideas_by_status": ideas_by_status,
        "jobs_total": sum(jobs_by_status.values()),
        "jobs_by_status": jobs_by_status,
    }

    await cache.set_json(key, data, settings.CACHE_TTL_DASHBOARD)
    return data
