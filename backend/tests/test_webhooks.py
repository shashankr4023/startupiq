"""CRUD tests for the webhook management endpoints."""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_create_list_delete_webhook(client: AsyncClient, user_id: uuid.UUID):
    headers = auth_header(user_id)

    resp = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook", "event_types": ["evaluation.completed"]},
        headers=headers,
    )
    assert resp.status_code == 201
    wh = resp.json()
    assert wh["target_url"] == "https://example.com/hook"
    assert wh["is_active"] is True
    assert len(wh["secret"]) >= 32  # a real generated secret was returned

    listed = await client.get("/api/v1/webhooks", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/api/v1/webhooks/{wh['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/webhooks", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_unsupported_event_type_rejected(client: AsyncClient, user_id: uuid.UUID):
    resp = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook", "event_types": ["not.a.real.event"]},
        headers=auth_header(user_id),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_webhook_ownership_enforced(client: AsyncClient, user_id: uuid.UUID):
    resp = await client.post(
        "/api/v1/webhooks",
        json={"target_url": "https://example.com/hook", "event_types": ["evaluation.completed"]},
        headers=auth_header(user_id),
    )
    wh_id = resp.json()["id"]

    other = uuid.uuid4()
    assert (await client.delete(f"/api/v1/webhooks/{wh_id}", headers=auth_header(other))).status_code == 404
    assert (await client.get(f"/api/v1/webhooks/{wh_id}/deliveries", headers=auth_header(other))).status_code == 404
