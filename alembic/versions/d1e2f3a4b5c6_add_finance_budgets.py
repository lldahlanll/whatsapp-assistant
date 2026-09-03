"""add_finance_budgets — personal finance budgeting table.

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4g5h6
Create Date: 2026-08-24

Adds table:
  - finance_budgets: budget per kategori per bulan
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "c1d2e3f4g5h6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finance_budgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_jid", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_jid", "category_id", "month", "year", name="uq_finance_budgets_owner_cat_month_year"),
    )
    with op.batch_alter_table("finance_budgets", schema=None) as batch_op:
        batch_op.create_index("ix_finance_budgets_owner_jid", ["owner_jid"], unique=False)
        batch_op.create_index("ix_finance_budgets_category_id", ["category_id"], unique=False)
        batch_op.create_index("ix_finance_budgets_period", ["year", "month"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("finance_budgets", schema=None) as batch_op:
        batch_op.drop_index("ix_finance_budgets_period")
        batch_op.drop_index("ix_finance_budgets_category_id")
        batch_op.drop_index("ix_finance_budgets_owner_jid")
    op.drop_table("finance_budgets")
