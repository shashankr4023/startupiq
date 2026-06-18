"""Evaluation endpoints.

Phase 3: the evaluation endpoint is now *asynchronous*. Instead of blocking for
10-20 seconds while the LLM thinks, it:

  1. creates a `jobs` row (status="queued"),
  2. enqueues an Arq background task,
  3. returns 202 Accepted immediately with a job id.

The slow LLM work happens in the worker (app/worker/tasks.py). The client polls
GET /api/v1/jobs/{job_id} (app/api/v1/jobs.py) to watch the status and collect
the result when it's done.
"""

from uuid import UUID, uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.arq import get_arq_pool
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.models.idea import StartupIdea
from app.db.models.job import Job
from app.db.session import AsyncSession, get_session
from app.llm.features import FeatureType

router = APIRouter(prefix="/ideas", tags=["evaluations"])


@router.post(
    "/{idea_id}/evaluations/{feature_type}",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(settings.RATE_LIMIT_EVALUATION)
async def request_evaluation(
    request: Request,  # required by slowapi's @limiter.limit
    idea_id: UUID,
    feature_type: FeatureType,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    pool: ArqRedis = Depends(get_arq_pool),
) -> dict:
    # Authorization: the idea must exist AND belong to the caller.
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    # 1. Record the job in Postgres (our durable source of truth).
    job = Job(
        id=uuid4(),
        user_id=user_id,
        idea_id=idea_id,
        feature_type=feature_type.value,
        status="queued",
    )
    session.add(job)
    await session.commit()

    # 2. Enqueue the work for the worker. We reuse the DB row's id as the Arq
    #    job id so the two stay in lock-step.
    await pool.enqueue_job("run_evaluation_feature", str(job.id), _job_id=str(job.id))

    # 3. Respond immediately - the client polls the status_url.
    return {
        "job_id": str(job.id),
        "status": job.status,
        "feature_type": feature_type.value,
        "status_url": f"/api/v1/jobs/{job.id}",
    }
