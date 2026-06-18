from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# The events a webhook can subscribe to. Fired by the worker when a job finishes.
SUPPORTED_EVENTS = {"evaluation.completed", "evaluation.failed"}


class WebhookCreate(BaseModel):
    target_url: str = Field(min_length=1)
    event_types: list[str] = Field(min_length=1)


class WebhookUpdate(BaseModel):
    target_url: str | None = None
    event_types: list[str] | None = None
    is_active: bool | None = None


class WebhookRead(BaseModel):
    id: UUID
    target_url: str
    event_types: list[str]
    is_active: bool
    secret: str  # shown so the user can configure their receiver's verification
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryRead(BaseModel):
    id: UUID
    event_type: str
    response_status: int | None
    attempt_count: int
    delivered_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
