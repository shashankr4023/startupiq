"""Tests for the async evaluation flow at the API level.

The endpoint no longer runs the LLM - it enqueues a job and returns 202. So here
we verify the *queuing* behavior (a job row is created and handed to the pool)
and the polling endpoint. The actual LLM work is tested in test_worker.py.
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header


async def _create_idea(client: AsyncClient, user_id: uuid.UUID) -> str:
    resp = await client.post(
        "/api/v1/ideas",
        json={"title": "AI Recipe Planner", "description": "Plans meals using AI"},
        headers=auth_header(user_id),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_request_evaluation_enqueues_job(
    client: AsyncClient, user_id: uuid.UUID, fake_pool
):
    idea_id = await _create_idea(client, user_id)

    resp = await client.post(
        f"/api/v1/ideas/{idea_id}/evaluations/competitor_research",
        headers=auth_header(user_id),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["feature_type"] == "competitor_research"
    job_id = body["job_id"]
    assert body["status_url"] == f"/api/v1/jobs/{job_id}"

    # The job was handed to the queue with the matching id.
    assert len(fake_pool.enqueued) == 1
    function, args, kwargs = fake_pool.enqueued[0]
    assert function == "run_evaluation_feature"
    assert args == (job_id,)
    assert kwargs["_job_id"] == job_id

    # And it's immediately pollable, in the queued state.
    poll = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_header(user_id))
    assert poll.status_code == 200
    assert poll.json()["status"] == "queued"
    assert poll.json()["result"] is None


@pytest.mark.asyncio
async def test_request_evaluation_on_unowned_idea_returns_404(
    client: AsyncClient, user_id: uuid.UUID, fake_pool
):
    idea_id = await _create_idea(client, user_id)
    other_user = uuid.uuid4()

    resp = await client.post(
        f"/api/v1/ideas/{idea_id}/evaluations/competitor_research",
        headers=auth_header(other_user),
    )
    assert resp.status_code == 404
    assert fake_pool.enqueued == []  # nothing queued for a rejected request


@pytest.mark.asyncio
async def test_invalid_feature_type_returns_422(
    client: AsyncClient, user_id: uuid.UUID, fake_pool
):
    idea_id = await _create_idea(client, user_id)

    resp = await client.post(
        f"/api/v1/ideas/{idea_id}/evaluations/not_a_real_feature",
        headers=auth_header(user_id),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_unowned_job_returns_404(
    client: AsyncClient, user_id: uuid.UUID, fake_pool
):
    idea_id = await _create_idea(client, user_id)
    resp = await client.post(
        f"/api/v1/ideas/{idea_id}/evaluations/competitor_research",
        headers=auth_header(user_id),
    )
    job_id = resp.json()["job_id"]

    other_user = uuid.uuid4()
    poll = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_header(other_user))
    assert poll.status_code == 404
