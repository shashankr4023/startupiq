from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class StartupIdea(SQLModel, table=True):
    __tablename__ = "startup_ideas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="profiles.id", index=True)
    title: str
    description: str
    industry: str | None = Field(default=None)
    target_market: str | None = Field(default=None)
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
