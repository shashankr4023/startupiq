"""Tests for the background worker task itself - the code that does the real LLM
work. We call `run_evaluation_feature` directly (no Redis, no Arq runtime), with
the test DB injected via the ctx and the LLM provider faked via monkeypatch.

This is the same lesson as Phase 2's fake provider: because the task depends on
`get_llm_provider()`, we can swap in a fake and test the whole task offline.
"""

import uuid

import pytest

from app.db.models.idea import StartupIdea
from app.db.models.job import Job
from app.db.models.profile import Profile
from app.llm.base import LLMProvider
from app.schemas.llm_results import Competitor, CompetitorResearchResult
from app.worker import tasks

CANNED = CompetitorResearchResult(
    summary="A moderately competitive space.",
    competitors=[
        Competitor(
            name="Acme Co",
            description="An incumbent.",
            strengths=["brand"],
            weaknesses=["slow"],
            differentiation="Be faster.",
        )
    ],
    market_saturation="medium - several established players",
)


class FakeProvider(LLMProvider):
    async def generate(self, *, system_prompt, user_prompt, schema):
        return CANNED

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model-1"


class FailingProvider(LLMProvider):
    async def generate(self, *, system_prompt, user_prompt, schema):
        raise RuntimeError("provider exploded")

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model-1"


async def _seed_job(session_maker, status="queued") -> uuid.UUID:
    uid = uuid.uuid4()
    idea_id = uuid.uuid4()
    job_id = uuid.uuid4()
    async with session_maker() as s:
        s.add(Profile(id=uid, email=f"{uid}@example.com"))
        s.add(StartupIdea(id=idea_id, user_id=uid, title="Idea", description="Desc"))
        s.add(
            Job(
                id=job_id,
                user_id=uid,
                idea_id=idea_id,
                feature_type="competitor_research",
                status=status,
            )
        )
        await s.commit()
    return job_id


@pytest.mark.asyncio
async def test_worker_completes_job(session_maker, monkeypatch):
    monkeypatch.setattr(tasks, "get_llm_provider", lambda: FakeProvider())
    job_id = await _seed_job(session_maker)

    result = await tasks.run_evaluation_feature({"session_maker": session_maker}, str(job_id))
    assert result == "completed"

    async with session_maker() as s:
        job = await s.get(Job, job_id)
    assert job.status == "completed"
    assert job.attempts == 1
    assert job.llm_provider == "fake"
    assert job.model_name == "fake-model-1"
    assert job.result_json["competitors"][0]["name"] == "Acme Co"
    assert job.error_message is None


@pytest.mark.asyncio
async def test_worker_marks_job_failed_on_provider_error(session_maker, monkeypatch):
    monkeypatch.setattr(tasks, "get_llm_provider", lambda: FailingProvider())
    job_id = await _seed_job(session_maker)

    result = await tasks.run_evaluation_feature({"session_maker": session_maker}, str(job_id))
    assert result == "failed"

    async with session_maker() as s:
        job = await s.get(Job, job_id)
    assert job.status == "failed"
    assert "provider exploded" in job.error_message
    assert job.result_json is None
