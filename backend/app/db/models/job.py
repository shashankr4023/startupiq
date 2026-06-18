from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    """A background job that runs one evaluation feature for an idea.

    This table *mirrors* the job's lifecycle in Postgres. Arq tracks jobs in
    Redis (where they expire), but we keep our own durable copy so the API and
    frontend can query status and read the result long after Redis forgets it.

    For Phase 3 the structured LLM result is stored directly here in
    `result_json`. (Later phases may normalise results into their own table once
    versioning/comparison features need it - for now, one row per job is simpler.)
    """

    __tablename__ = "jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)  # also the Arq job id
    user_id: UUID = Field(foreign_key="profiles.id", index=True)
    idea_id: UUID = Field(foreign_key="startup_ideas.id", index=True)

    job_type: str = Field(default="run_evaluation")
    feature_type: str

    # queued -> running -> completed | failed
    status: str = Field(default="queued", index=True)
    attempts: int = Field(default=0)

    # Populated once the worker finishes successfully:
    result_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    llm_provider: str | None = Field(default=None)
    model_name: str | None = Field(default=None)

    # Populated if the job fails:
    error_message: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
