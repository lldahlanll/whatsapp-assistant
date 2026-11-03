"""finance_soft_delete — kolom deleted_at pada finance_transactions.

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-11-03

Menghapus transaksi tidak lagi menghapus baris; baris ditandai deleted_at (+ is_reversed)
sehingga jejak audit tetap ada dan laporan tetap mengabaikannya.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
