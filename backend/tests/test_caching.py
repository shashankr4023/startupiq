"""Tests for caching behavior on the idea-detail and dashboard endpoints.

We use the InMemoryCache (injected by the conftest `client` fixture) and prove
two things: a read populates and is then served from the cache, and a write
invalidates it.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.idea import StartupIdea
from tests.conftest import auth_header


async def _create_idea(client: AsyncClient, user_id: uuid.UUID, title="Original") -> str:
    resp = await client.post(
        "/api/v1/ideas",
        json={"title": title, "description": "Desc"},
        headers=auth_header(user_id),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_idea_detail_is_cached_and_invalidated_on_write(
    client: AsyncClient, user_id: uuid.UUID, session: AsyncSession, cache
):
    idea_id = await _create_idea(client, user_id, title="Original")

    # First GET: cache miss -> populates the cache.
    r1 = await client.get(f"/api/v1/ideas/{idea_id}", headers=auth_header(user_id))
    assert r1.json()["title"] == "Original"
    assert cache._store  # something was cached

    # Mutate the row DIRECTLY in the DB (no API write -> no invalidation).
    idea = await session.get(StartupIdea, uuid.UUID(idea_id))
    idea.title = "Changed behind the cache's back"
    session.add(idea)
    await session.commit()

    # Second GET still returns the OLD value -> proves it was served from cache.
    r2 = await client.get(f"/api/v1/ideas/{idea_id}", headers=auth_header(user_id))
    assert r2.json()["title"] == "Original"

    # A PATCH through the API invalidates the cache...
    await client.patch(
        f"/api/v1/ideas/{idea_id}",
        json={"title": "Updated via API"},
        headers=auth_header(user_id),
    )
    # ...so the next GET reflects the new value.
    r3 = await client.get(f"/api/v1/ideas/{idea_id}", headers=auth_header(user_id))
    assert r3.json()["title"] == "Updated via API"


@pytest.mark.asyncio
async def test_dashboard_stats_counts_and_caches(
    client: AsyncClient, user_id: uuid.UUID, fake_pool
):
    await _create_idea(client, user_id)
    idea_id = await _create_idea(client, user_id)
    # Queue one evaluation job so jobs show up in the stats.
    await client.post(
        f"/api/v1/ideas/{idea_id}/evaluations/competitor_research",
        headers=auth_header(user_id),
    )

    r1 = await client.get("/api/v1/dashboard/stats", headers=auth_header(user_id))
    assert r1.status_code == 200
    stats = r1.json()
    assert stats["ideas_total"] == 2
    assert stats["jobs_total"] == 1
    assert stats["jobs_by_status"]["queued"] == 1

    # Add another idea, then fetch again: result is unchanged because the stats
    # are served from cache (TTL-based) until they expire.
    await _create_idea(client, user_id)
    r2 = await client.get("/api/v1/dashboard/stats", headers=auth_header(user_id))
    assert r2.json()["ideas_total"] == 2  # still cached
