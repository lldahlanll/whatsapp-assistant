"""harden_finance_transactions — add immutability, idempotency, human_tx_id to finance_transactions.

Revision ID: c1d2e3f4g5h6
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4g5h6"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("human_tx_id", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("is_reversed", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("reversal_of_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_finance_transactions_human_tx_id", ["human_tx_id"], unique=False)
        batch_op.create_index("ix_finance_transactions_idempotency_key", ["idempotency_key"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.drop_index("ix_finance_transactions_idempotency_key")
        batch_op.drop_index("ix_finance_transactions_human_tx_id")
        batch_op.drop_column("reversal_of_id")
        batch_op.drop_column("is_reversed")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("human_tx_id")
