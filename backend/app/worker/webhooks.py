"""Webhook delivery - the event-driven, reliable half of Phase 7.

Flow when an evaluation job finishes (see app/worker/tasks.py):

  run_evaluation_feature  ──enqueues──▶  dispatch_webhook_event(user, event, payload)
                                              │  finds the user's matching webhooks
                                              │  creates a delivery row per webhook
                                              └──enqueues──▶  deliver_webhook(delivery_id)
                                                                  POSTs the signed payload,
                                                                  retries on failure.

Splitting "fan-out" (dispatch) from "one POST" (deliver) means each webhook gets
its own independently-retried delivery job - a failure to one subscriber never
re-sends to the others.
"""

import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

import httpx
from arq import Retry
from sqlmodel import select

from app.db.models.webhook import Webhook, WebhookDelivery

MAX_TRIES = 5            # give up after this many delivery attempts
REQUEST_TIMEOUT = 10.0   # seconds


def sign(secret: str, body: bytes) -> str:
    """HMAC-SHA256 of the exact request body, keyed by the webhook's secret.

    The receiver recomputes this over the bytes they receive and compares - if
    it matches, the request provably came from someone who knows the secret
    (us), and wasn't tampered with in transit.
    """
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    """Do the actual HTTP POST. Isolated so tests can monkeypatch it."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(url, content=body, headers=headers)
        return resp.status_code


async def dispatch_webhook_event(
    ctx: dict, user_id: str, event_type: str, payload: dict
) -> str:
    """Fan-out: find the user's active webhooks subscribed to this event, create
    a delivery audit row for each, and enqueue an individual delivery job."""
    session_maker = ctx["session_maker"]
    redis = ctx.get("redis")

    async with session_maker() as session:
        result = await session.execute(
            select(Webhook).where(
                Webhook.user_id == UUID(user_id),
                Webhook.is_active.is_(True),
            )
        )
        webhooks = result.scalars().all()

        dispatched = 0
        for wh in webhooks:
            if event_type not in (wh.event_types or []):
                continue
            delivery = WebhookDelivery(
                webhook_id=wh.id, event_type=event_type, payload_json=payload
            )
            session.add(delivery)
            await session.commit()
            await session.refresh(delivery)
            if redis is not None:
                await redis.enqueue_job("deliver_webhook", str(delivery.id))
            dispatched += 1

    return f"dispatched:{dispatched}"


async def deliver_webhook(ctx: dict, delivery_id: str) -> str:
    """POST one signed payload to one webhook, recording the outcome and
    retrying with backoff on failure."""
    session_maker = ctx["session_maker"]
    attempt = ctx.get("job_try", 1)

    async with session_maker() as session:
        delivery = await session.get(WebhookDelivery, UUID(delivery_id))
        if delivery is None:
            return "delivery-not-found"
        webhook = await session.get(Webhook, delivery.webhook_id)
        if webhook is None or not webhook.is_active:
            return "webhook-inactive"

        # Serialise once, sign those exact bytes, send those exact bytes.
        body = json.dumps(delivery.payload_json, separators=(",", ":")).encode()
        headers = {
            "Content-Type": "application/json",
            "X-StartupIQ-Event": delivery.event_type,
            "X-StartupIQ-Signature": f"sha256={sign(webhook.secret, body)}",
        }

        delivery.attempt_count = attempt
        try:
            status_code: int | None = await _post(webhook.target_url, body, headers)
        except Exception:  # noqa: BLE001 - network error, treat as a failed attempt
            status_code = None

        delivery.response_status = status_code
        success = status_code is not None and 200 <= status_code < 300
        if success:
            delivery.delivered_at = datetime.utcnow()
        await session.commit()

    if success:
        return "delivered"
    if attempt < MAX_TRIES:
        # Reschedule with exponential backoff (Arq increments job_try each retry).
        raise Retry(defer=2**attempt)
    return "failed"
