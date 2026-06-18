"""The actual background work.

`run_evaluation_feature` is the function the Arq worker runs when it picks a job
off the queue. It does the slow LLM call that we *used* to do inline in the API
(Phase 2), and records the outcome on the job row.

It takes only `job_id` - every other piece of state (idea, feature type, owner)
lives on the job row in Postgres, so the worker is fully self-contained: hand it
a job id and it does the rest.
"""

from datetime import datetime
from uuid import UUID

from app.db.models.idea import StartupIdea
from app.db.models.job import Job
from app.llm.factory import get_llm_provider
from app.llm.features import FEATURES, FeatureType, SYSTEM_PROMPT, build_user_prompt


async def run_evaluation_feature(ctx: dict, job_id: str) -> str:
    """Run one evaluation feature and store the result on the job row.

    `ctx` is Arq's per-worker context dict; we read the DB session factory that
    `WorkerSettings.on_startup` placed there. Returns a short status string that
    Arq stores as the job result in Redis (handy when tailing worker logs).
    """
    session_maker = ctx["session_maker"]

    async with session_maker() as session:
        job = await session.get(Job, UUID(job_id))
        if job is None:
            return "job-not-found"

        # Mark as running so a poller sees progress.
        job.status = "running"
        job.attempts += 1
        job.updated_at = datetime.utcnow()
        await session.commit()

        idea = await session.get(StartupIdea, job.idea_id)
        if idea is None:
            job.status = "failed"
            job.error_message = "Idea no longer exists"
            job.updated_at = datetime.utcnow()
            await session.commit()
            return "idea-missing"

        spec = FEATURES[FeatureType(job.feature_type)]
        provider = get_llm_provider()

        try:
            result = await provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_user_prompt(idea, spec),
                schema=spec.result_schema,
            )
            job.result_json = result.model_dump()
            job.llm_provider = provider.name
            job.model_name = provider.model
            job.status = "completed"
        except Exception as exc:  # noqa: BLE001 - record any provider failure on the job
            job.status = "failed"
            job.error_message = str(exc)

        job.updated_at = datetime.utcnow()
        await session.commit()

        # Fire an event so any registered webhooks get notified. We enqueue a
        # separate dispatch job (via the pool Arq puts in ctx) rather than POST
        # inline, keeping this task focused on the evaluation itself.
        redis = ctx.get("redis")
        if redis is not None:
            event = (
                "evaluation.completed" if job.status == "completed" else "evaluation.failed"
            )
            await redis.enqueue_job(
                "dispatch_webhook_event",
                str(job.user_id),
                event,
                {
                    "event": event,
                    "job_id": str(job.id),
                    "idea_id": str(job.idea_id),
                    "feature_type": job.feature_type,
                    "status": job.status,
                    "result": job.result_json,
                },
            )

        return job.status
