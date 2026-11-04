"""budget_recurring — kolom is_recurring pada finance_budgets.

Revision ID: g1a2b3c4d5e6
Revises: f1a2b3c4d5e6
Create Date: 2026-11-04

Budget otomatis disalin ke bulan berikutnya selama is_recurring = 1.
Baris yang sudah ada dianggap berulang.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("finance_budgets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )


def downgrade() -> None:
    with op.batch_alter_table("finance_budgets", schema=None) as batch_op:
        batch_op.drop_column("is_recurring")
