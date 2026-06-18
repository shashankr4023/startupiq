"""Webhook subscription management.

Users register a target URL + the events they care about; we hand back a
generated `secret` they use to verify our signed payloads. The actual delivery
happens in the worker (app/worker/webhooks.py); these endpoints just manage the
registrations and expose the delivery audit log.
"""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.core.security import get_current_user
from app.db.models.webhook import Webhook, WebhookDelivery
from app.db.session import AsyncSession, get_session
from app.schemas.webhook import (
    SUPPORTED_EVENTS,
    WebhookCreate,
    WebhookDeliveryRead,
    WebhookRead,
    WebhookUpdate,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_events(event_types: list[str]) -> None:
    unknown = set(event_types) - SUPPORTED_EVENTS
    if unknown:
        raise HTTPException(
            status_code=422,  # Unprocessable Content
            detail=f"Unsupported event types: {sorted(unknown)}. "
            f"Supported: {sorted(SUPPORTED_EVENTS)}",
        )


async def _get_owned(session: AsyncSession, webhook_id: UUID, user_id: UUID) -> Webhook:
    wh = await session.get(Webhook, webhook_id)
    if wh is None or wh.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return wh


@router.post("", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Webhook:
    _validate_events(payload.event_types)
    wh = Webhook(
        user_id=user_id,
        target_url=payload.target_url,
        event_types=payload.event_types,
        secret=secrets.token_hex(32),  # generated server-side
    )
    session.add(wh)
    await session.commit()
    await session.refresh(wh)
    return wh


@router.get("", response_model=list[WebhookRead])
async def list_webhooks(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Webhook]:
    result = await session.execute(select(Webhook).where(Webhook.user_id == user_id))
    return list(result.scalars().all())


@router.patch("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdate,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Webhook:
    wh = await _get_owned(session, webhook_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if "event_types" in updates:
        _validate_events(updates["event_types"])
    for field, value in updates.items():
        setattr(wh, field, value)
    session.add(wh)
    await session.commit()
    await session.refresh(wh)
    return wh


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    wh = await _get_owned(session, webhook_id, user_id)
    await session.delete(wh)
    await session.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_deliveries(
    webhook_id: UUID,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WebhookDelivery]:
    await _get_owned(session, webhook_id, user_id)  # ownership check
    result = await session.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
    )
    return list(result.scalars().all())
