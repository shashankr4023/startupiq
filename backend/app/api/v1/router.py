from fastapi import APIRouter

from app.api.v1 import dashboard, evaluations, ideas, jobs, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ideas.router)
api_router.include_router(evaluations.router)
api_router.include_router(jobs.router)
api_router.include_router(dashboard.router)
api_router.include_router(webhooks.router)
