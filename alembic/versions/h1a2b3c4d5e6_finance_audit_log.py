"""finance_audit_log — riwayat data finance yang dihapus.

Revision ID: h1a2b3c4d5e6
Revises: g1a2b3c4d5e6
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "g1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_jid", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_finance_audit_log_owner_created", "finance_audit_log", ["owner_jid", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_finance_audit_log_owner_created", table_name="finance_audit_log")
    op.drop_table("finance_audit_log")
