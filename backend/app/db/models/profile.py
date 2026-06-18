from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


class Profile(SQLModel, table=True):
    """Mirrors auth.users (1:1), populated via a Postgres trigger on signup."""

    __tablename__ = "profiles"

    id: UUID = Field(primary_key=True)
    email: str = Field(index=True)
    display_name: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
