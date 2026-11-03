"""finance_unique_guards — unique index kategori & idempotency_key, plus cleanup duplikat lama.

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-11-03

Perubahan:
  - Gabungkan kategori duplikat (akibat seed default yang berjalan bersamaan) per
    (owner_jid, category_type, name); transaksi & budget dipindahkan ke kategori yang dipertahankan.
  - Kosongkan idempotency_key pada baris duplikat (uang tidak disentuh; baris pertama tetap
    memegang kunci). Duplikat semacam itu adalah transaksi ganda nyata yang perlu ditinjau manual.
  - Tambah unique index agar kedua kasus tidak bisa terjadi lagi.
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def _dedupe_categories(conn: sa.Connection) -> None:
    groups = conn.execute(
        sa.text(
            "SELECT owner_jid, category_type, name FROM finance_categories "
            "GROUP BY owner_jid, category_type, name HAVING COUNT(*) > 1"
        )
    ).fetchall()
    removed = 0
    for owner, ctype, name in groups:
        ids = [
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT id FROM finance_categories "
                    "WHERE owner_jid = :o AND category_type = :t AND name = :n "
                    "ORDER BY created_at, id"
                ),
                {"o": owner, "t": ctype, "n": name},
            )
        ]
        keeper, dups = ids[0], ids[1:]
        for dup in dups:
            params = {"keeper": keeper, "dup": dup}
            conn.execute(
                sa.text("UPDATE finance_transactions SET category_id = :keeper WHERE category_id = :dup"),
                params,
            )
            # Budget unik per (owner, kategori, bulan, tahun): buang yang bentrok, pindahkan sisanya.
            conn.execute(
                sa.text(
                    "DELETE FROM finance_budgets WHERE category_id = :dup AND EXISTS ("
                    "SELECT 1 FROM finance_budgets k WHERE k.category_id = :keeper "
                    "AND k.owner_jid = finance_budgets.owner_jid "
                    "AND k.month = finance_budgets.month AND k.year = finance_budgets.year)"
                ),
                params,
            )
            conn.execute(
                sa.text("UPDATE finance_budgets SET category_id = :keeper WHERE category_id = :dup"),
                params,
            )
            conn.execute(sa.text("DELETE FROM finance_categories WHERE id = :dup"), {"dup": dup})
            removed += 1
    if removed:
        log.warning("finance_unique_guards: merged %d duplicate categories", removed)


def _clear_duplicate_idempotency_keys(conn: sa.Connection) -> None:
    result = conn.execute(
        sa.text(
            "UPDATE finance_transactions SET idempotency_key = NULL "
            "WHERE idempotency_key IS NOT NULL AND id NOT IN ("
            "SELECT id FROM finance_transactions t WHERE t.idempotency_key IS NOT NULL "
            "AND t.rowid = (SELECT MIN(t2.rowid) FROM finance_transactions t2 "
            "WHERE t2.owner_jid = t.owner_jid AND t2.idempotency_key = t.idempotency_key))"
        )
    )
    if result.rowcount:
        log.warning(
            "finance_unique_guards: %d duplicate transactions had their idempotency_key cleared; "
            "review them for double entries",
            result.rowcount,
        )


def upgrade() -> None:
    conn = op.get_bind()
    _dedupe_categories(conn)
    _clear_duplicate_idempotency_keys(conn)

    op.create_index(
        "uq_finance_categories_owner_type_name",
        "finance_categories",
        ["owner_jid", "category_type", "name"],
        unique=True,
    )
    op.create_index(
        "uq_finance_transactions_owner_idem",
        "finance_transactions",
        ["owner_jid", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_finance_transactions_owner_idem", table_name="finance_transactions")
    op.drop_index("uq_finance_categories_owner_type_name", table_name="finance_categories")
