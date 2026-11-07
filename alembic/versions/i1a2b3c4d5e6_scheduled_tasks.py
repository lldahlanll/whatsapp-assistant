"""scheduled_tasks — pengingat & laporan keuangan terjadwal.

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "h1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_jid", sa.String(100), nullable=False),
        sa.Column("chat_jid", sa.String(100), nullable=False),
        sa.Column("short_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recurrence", sa.String(20), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("anchor_day", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_jid", "short_id", name="uq_scheduled_tasks_owner_short_id"),
    )
    op.create_index("ix_scheduled_tasks_due", "scheduled_tasks", ["is_active", "next_run_at"])
    op.create_index("ix_scheduled_tasks_owner", "scheduled_tasks", ["owner_jid", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_owner", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_due", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
