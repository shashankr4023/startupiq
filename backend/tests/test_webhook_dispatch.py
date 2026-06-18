"""Tests for the worker-side webhook machinery: signing, fan-out dispatch, and
delivery (success + failure/retry). No real HTTP - `_post` is monkeypatched."""

import hashlib
import hmac
import uuid

import pytest
from arq import Retry

from app.db.models.profile import Profile
from app.db.models.webhook import Webhook, WebhookDelivery
from app.worker import webhooks
from tests.conftest import FakePool


def test_sign_is_verifiable():
    secret = "topsecret"
    body = b'{"hello":"world"}'
    sig = webhooks.sign(secret, body)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sig == expected


async def _seed_user(session_maker) -> uuid.UUID:
    uid = uuid.uuid4()
    async with session_maker() as s:
        s.add(Profile(id=uid, email=f"{uid}@example.com"))
        await s.commit()
    return uid


async def _add_webhook(session_maker, user_id, events, active=True) -> uuid.UUID:
    wid = uuid.uuid4()
    async with session_maker() as s:
        s.add(
            Webhook(
                id=wid,
                user_id=user_id,
                target_url="https://example.com/hook",
                secret="s3cr3t",
                event_types=events,
                is_active=active,
            )
        )
        await s.commit()
    return wid


@pytest.mark.asyncio
async def test_dispatch_fans_out_to_matching_active_webhooks(session_maker):
    user_id = await _seed_user(session_maker)
    match = await _add_webhook(session_maker, user_id, ["evaluation.completed"])
    await _add_webhook(session_maker, user_id, ["evaluation.failed"])  # wrong event
    await _add_webhook(session_maker, user_id, ["evaluation.completed"], active=False)  # inactive

    pool = FakePool()
    ctx = {"session_maker": session_maker, "redis": pool}
    out = await webhooks.dispatch_webhook_event(
        ctx, str(user_id), "evaluation.completed", {"event": "evaluation.completed"}
    )

    assert out == "dispatched:1"  # only the matching active webhook
    assert len(pool.enqueued) == 1
    assert pool.enqueued[0][0] == "deliver_webhook"

    # A delivery audit row was created for the matching webhook only.
    async with session_maker() as s:
        from sqlmodel import select

        rows = (await s.execute(select(WebhookDelivery))).scalars().all()
    assert len(rows) == 1
    assert rows[0].webhook_id == match


async def _seed_delivery(session_maker, webhook_id) -> uuid.UUID:
    did = uuid.uuid4()
    async with session_maker() as s:
        s.add(
            WebhookDelivery(
                id=did,
                webhook_id=webhook_id,
                event_type="evaluation.completed",
                payload_json={"event": "evaluation.completed"},
            )
        )
        await s.commit()
    return did


@pytest.mark.asyncio
async def test_deliver_success(session_maker, monkeypatch):
    user_id = await _seed_user(session_maker)
    wid = await _add_webhook(session_maker, user_id, ["evaluation.completed"])
    did = await _seed_delivery(session_maker, wid)

    async def fake_post(url, body, headers):
        assert headers["X-StartupIQ-Signature"].startswith("sha256=")
        return 200

    monkeypatch.setattr(webhooks, "_post", fake_post)

    out = await webhooks.deliver_webhook({"session_maker": session_maker, "job_try": 1}, str(did))
    assert out == "delivered"

    async with session_maker() as s:
        d = await s.get(WebhookDelivery, did)
    assert d.response_status == 200
    assert d.delivered_at is not None
    assert d.attempt_count == 1


@pytest.mark.asyncio
async def test_deliver_failure_retries_then_gives_up(session_maker, monkeypatch):
    user_id = await _seed_user(session_maker)
    wid = await _add_webhook(session_maker, user_id, ["evaluation.completed"])
    did = await _seed_delivery(session_maker, wid)

    async def failing_post(url, body, headers):
        return 500

    monkeypatch.setattr(webhooks, "_post", failing_post)

    # Early attempt -> records the failure and asks Arq to retry.
    with pytest.raises(Retry):
        await webhooks.deliver_webhook({"session_maker": session_maker, "job_try": 1}, str(did))

    async with session_maker() as s:
        d = await s.get(WebhookDelivery, did)
    assert d.response_status == 500
    assert d.delivered_at is None

    # Final attempt -> gives up cleanly (no further retry).
    out = await webhooks.deliver_webhook(
        {"session_maker": session_maker, "job_try": webhooks.MAX_TRIES}, str(did)
    )
    assert out == "failed"
