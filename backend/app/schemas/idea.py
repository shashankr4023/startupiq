from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    industry: str | None = None
    target_market: str | None = None


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    industry: str | None = None
    target_market: str | None = None
    status: str | None = None


class IdeaRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: str
    industry: str | None
    target_market: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
