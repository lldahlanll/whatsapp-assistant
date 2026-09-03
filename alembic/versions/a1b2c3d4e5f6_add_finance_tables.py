"""add_finance_tables — personal finance tracking tables.

Revision ID: a1b2c3d4e5f6
Revises: 9b642d3a9527
Create Date: 2026-08-18

Adds three tables:
  - finance_accounts    : rekening/dompet milik user
  - finance_categories  : kategori transaksi (bawaan + custom)
  - finance_transactions: riwayat transaksi keuangan
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "9b642d3a9527"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_jid", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False, server_default="cash"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="IDR"),
        sa.Column("balance", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("finance_accounts", schema=None) as batch_op:
        batch_op.create_index("ix_finance_accounts_owner_jid", ["owner_jid"], unique=False)

    op.create_table(
        "finance_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_jid", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category_type", sa.String(length=20), nullable=False),
        sa.Column("icon", sa.String(length=10), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("finance_categories", schema=None) as batch_op:
        batch_op.create_index("ix_finance_categories_owner_jid", ["owner_jid"], unique=False)

    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_jid", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transaction_date", sa.DateTime(), nullable=False),
        sa.Column("transfer_to_account_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.create_index("ix_finance_transactions_owner_jid", ["owner_jid"], unique=False)
        batch_op.create_index("ix_finance_transactions_date", ["transaction_date"], unique=False)
        batch_op.create_index("ix_finance_transactions_account_id", ["account_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("finance_transactions", schema=None) as batch_op:
        batch_op.drop_index("ix_finance_transactions_account_id")
        batch_op.drop_index("ix_finance_transactions_date")
        batch_op.drop_index("ix_finance_transactions_owner_jid")
    op.drop_table("finance_transactions")

    with op.batch_alter_table("finance_categories", schema=None) as batch_op:
        batch_op.drop_index("ix_finance_categories_owner_jid")
    op.drop_table("finance_categories")

    with op.batch_alter_table("finance_accounts", schema=None) as batch_op:
        batch_op.drop_index("ix_finance_accounts_owner_jid")
    op.drop_table("finance_accounts")
