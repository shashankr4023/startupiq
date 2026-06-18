import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.profile import Profile
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_create_list_get_idea(client: AsyncClient, user_id: uuid.UUID):
    headers = auth_header(user_id)

    create_resp = await client.post(
        "/api/v1/ideas",
        json={"title": "AI Recipe Planner", "description": "Plans meals using AI"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    idea = create_resp.json()
    assert idea["title"] == "AI Recipe Planner"

    list_resp = await client.get("/api/v1/ideas", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = await client.get(f"/api/v1/ideas/{idea['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == idea["id"]


@pytest.mark.asyncio
async def test_get_idea_not_owned_returns_404(
    client: AsyncClient, user_id: uuid.UUID, session: AsyncSession
):
    create_resp = await client.post(
        "/api/v1/ideas",
        json={"title": "Idea", "description": "Desc"},
        headers=auth_header(user_id),
    )
    idea_id = create_resp.json()["id"]

    other_user = uuid.uuid4()
    session.add(Profile(id=other_user, email=f"{other_user}@example.com"))
    await session.commit()

    resp = await client.get(f"/api/v1/ideas/{idea_id}", headers=auth_header(other_user))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_and_soft_delete_idea(client: AsyncClient, user_id: uuid.UUID):
    headers = auth_header(user_id)
    create_resp = await client.post(
        "/api/v1/ideas",
        json={"title": "Idea", "description": "Desc"},
        headers=headers,
    )
    idea_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/ideas/{idea_id}",
        json={"title": "Updated title"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated title"

    delete_resp = await client.delete(f"/api/v1/ideas/{idea_id}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/ideas/{idea_id}", headers=headers)
    assert get_resp.json()["status"] == "archived"
