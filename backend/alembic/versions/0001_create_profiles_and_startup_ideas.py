"""create profiles and startup_ideas

Revision ID: 0001
Revises:
Create Date: 2026-06-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # id matches auth.users.id (Supabase-managed table)
        sa.ForeignKeyConstraint(["id"], ["auth.users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_profiles_email"), "profiles", ["email"], unique=False)

    op.create_table(
        "startup_ideas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("industry", sa.String(), nullable=True),
        sa.Column("target_market", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_startup_ideas_user_id"), "startup_ideas", ["user_id"], unique=False)
    op.create_index(op.f("ix_startup_ideas_status"), "startup_ideas", ["status"], unique=False)
    op.create_index(op.f("ix_startup_ideas_created_at"), "startup_ideas", ["created_at"], unique=False)
    op.create_index(
        "ix_startup_ideas_user_id_created_at",
        "startup_ideas",
        ["user_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_startup_ideas_user_id_created_at", table_name="startup_ideas")
    op.drop_index(op.f("ix_startup_ideas_created_at"), table_name="startup_ideas")
    op.drop_index(op.f("ix_startup_ideas_status"), table_name="startup_ideas")
    op.drop_index(op.f("ix_startup_ideas_user_id"), table_name="startup_ideas")
    op.drop_table("startup_ideas")

    op.drop_index(op.f("ix_profiles_email"), table_name="profiles")
    op.drop_table("profiles")
