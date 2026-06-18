"""add trigger to auto-create profile on new auth.users row

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        create or replace function public.handle_new_user()
        returns trigger as $$
        begin
          insert into public.profiles (id, email, created_at)
          values (new.id, new.email, now());
          return new;
        end;
        $$ language plpgsql security definer set search_path = public;
        """
    )
    op.execute(
        """
        create trigger on_auth_user_created
          after insert on auth.users
          for each row execute procedure public.handle_new_user();
        """
    )


def downgrade() -> None:
    op.execute("drop trigger if exists on_auth_user_created on auth.users;")
    op.execute("drop function if exists public.handle_new_user();")
