"""Arq worker configuration.

Run the worker (in its own terminal / its own process) with:

    arq app.worker.settings.WorkerSettings

Arq reads this class to learn which Redis to connect to, which task functions
exist, and what to do on startup/shutdown. The worker is a *separate process*
from the API - that separation is the whole point: slow LLM work happens here,
keeping the API fast and responsive.
"""

from app.core.arq import get_redis_settings
from app.db.session import async_session_maker
from app.worker.tasks import run_evaluation_feature
from app.worker.webhooks import deliver_webhook, dispatch_webhook_event


async def startup(ctx: dict) -> None:
    # Give every task access to a DB session factory via the shared context.
    ctx["session_maker"] = async_session_maker


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [run_evaluation_feature, dispatch_webhook_event, deliver_webhook]
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    # How many jobs this worker runs concurrently. Tunable later for scale.
    max_jobs = 10
