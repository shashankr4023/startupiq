"""Job status endpoint - the polling half of the async evaluation flow.

After POSTing an evaluation request (which returns a job id), the client polls
GET /api/v1/jobs/{job_id} until status is "completed" (read `result`) or
"failed" (read `error_message`).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.db.models.job import Job
from app.db.session import AsyncSession, get_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return {
        "job_id": str(job.id),
        "idea_id": str(job.idea_id),
        "feature_type": job.feature_type,
        "status": job.status,
        "attempts": job.attempts,
        "llm_provider": job.llm_provider,
        "model": job.model_name,
        "result": job.result_json,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
