from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Webhook(SQLModel, table=True):
    """A user's registration to be POSTed when an event happens.

    `secret` is used to HMAC-sign every payload so the receiver can verify the
    request really came from us. `event_types` is the list of events this
    subscription cares about (e.g. ["evaluation.completed"]).
    """

    __tablename__ = "webhooks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="profiles.id", index=True)
    target_url: str
    secret: str
    event_types: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WebhookDelivery(SQLModel, table=True):
    """An audit record of one attempt to deliver an event to one webhook.

    One row is created per (event, webhook) pair the moment dispatch begins, then
    updated as delivery is attempted (and retried). This is the reliability
    ledger - you can always see what was sent, when, and whether it succeeded.
    """

    __tablename__ = "webhook_deliveries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    webhook_id: UUID = Field(foreign_key="webhooks.id", index=True)
    event_type: str
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    response_status: int | None = Field(default=None)
    attempt_count: int = Field(default=0)
    delivered_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
