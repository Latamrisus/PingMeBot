"""add telegram_user_id to tasks

Revision ID: 9d0b2d4f1c90
Revises: e4505e821e13
Create Date: 2026-03-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d0b2d4f1c90"
down_revision: Union[str, Sequence[str], None] = "e4505e821e13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_tasks_telegram_user_id"), "tasks", ["telegram_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_telegram_user_id"), table_name="tasks")
    op.drop_column("tasks", "telegram_user_id")
