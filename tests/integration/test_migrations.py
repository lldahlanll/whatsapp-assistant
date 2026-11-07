"""Pastikan migrasi Alembic aman dijalankan otomatis saat deploy."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import whatsapp_platform.infrastructure.database.models
from alembic import command
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.migration_backup import (
    backup_before_migration,
    sqlite_path_from_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIRST_FINANCE_REVISION = "a1b2c3d4e5f6"


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def _alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


def test_models_match_migrations(db_url: str, tmp_path: Path) -> None:
    """Gagal jika model diubah tanpa membuat file migrasi baru."""
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"Model berubah tanpa migrasi Alembic: {diff}"


def test_migrations_upgrade_downgrade_roundtrip(db_url: str) -> None:
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_backup_created_only_when_migration_pending(db_url: str, tmp_path: Path) -> None:
    config = _alembic_config()
    command.upgrade(config, FIRST_FINANCE_REVISION)

    backup = backup_before_migration(db_url, PROJECT_ROOT)
    assert backup is not None
    assert backup.parent == tmp_path / "backups"
    assert FIRST_FINANCE_REVISION in backup.name

    command.upgrade(config, "head")
    assert backup_before_migration(db_url, PROJECT_ROOT) is None


def test_backup_prunes_old_copies(db_url: str, tmp_path: Path) -> None:
    command.upgrade(_alembic_config(), FIRST_FINANCE_REVISION)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for i in range(5):
        (backup_dir / f"app-old-{i}.db").write_bytes(b"")

    backup_before_migration(db_url, PROJECT_ROOT, keep=3)
    assert len(list(backup_dir.glob("app-*.db"))) == 3


def test_backup_skips_missing_or_non_sqlite_db(tmp_path: Path) -> None:
    assert backup_before_migration(f"sqlite+aiosqlite:///{tmp_path / 'none.db'}", PROJECT_ROOT) is None
    assert sqlite_path_from_url("postgresql+asyncpg://u:p@localhost/db", PROJECT_ROOT) is None
    assert sqlite_path_from_url("sqlite+aiosqlite:///:memory:", PROJECT_ROOT) is None
    assert sqlite_path_from_url("sqlite+aiosqlite:///./storage/x.db", tmp_path) == tmp_path / "storage/x.db"


def test_unique_guards_migration_cleans_existing_duplicates(db_url: str, tmp_path: Path) -> None:
    """Duplikat lama (kategori ganda, idempotency_key ganda) dirapikan tanpa menghilangkan uang/budget."""
    import sqlite3

    config = _alembic_config()
    command.upgrade(config, "d1e2f3a4b5c6")
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    now = "2026-11-01 00:00:00"
    owner = "628111@s.whatsapp.net"
    for cat_id, created in (("cat-keep", "2026-11-01 00:00:00"), ("cat-dup", "2026-11-01 00:00:01")):
        conn.execute(
            "INSERT INTO finance_categories (id, owner_jid, name, category_type, is_default, created_at) "
            "VALUES (?, ?, 'Makanan', 'expense', 1, ?)",
            (cat_id, owner, created),
        )
    transactions = (("tx1", "wa:M1:a", "cat-keep"), ("tx2", "wa:M1:a", "cat-dup"), ("tx3", "wa:M2:b", "cat-dup"))
    for tx_id, key, cat in transactions:
        conn.execute(
            "INSERT INTO finance_transactions (id, owner_jid, account_id, transaction_type, amount, category_id, "
            "transaction_date, created_at, idempotency_key) VALUES (?, ?, 'acc', 'expense', 10000, ?, ?, ?, ?)",
            (tx_id, owner, cat, now, now, key),
        )
    # Budget bentrok (bulan sama) pada kategori duplikat + budget bulan lain yang harus dipindahkan.
    for b_id, cat, month in (("b1", "cat-keep", 11), ("b2", "cat-dup", 11), ("b3", "cat-dup", 12)):
        conn.execute(
            "INSERT INTO finance_budgets (id, owner_jid, category_id, amount, month, year, created_at, updated_at) "
            "VALUES (?, ?, ?, 500000, ?, 2026, ?, ?)",
            (b_id, owner, cat, month, now, now),
        )
    conn.commit()
    conn.close()

    command.upgrade(config, "head")

    conn = sqlite3.connect(db)
    try:
        assert [r[0] for r in conn.execute("SELECT id FROM finance_categories")] == ["cat-keep"]
        assert {r[0] for r in conn.execute("SELECT category_id FROM finance_transactions")} == {"cat-keep"}
        # Tidak ada transaksi yang hilang; hanya idempotency_key duplikat yang dikosongkan.
        keys = dict(conn.execute("SELECT id, idempotency_key FROM finance_transactions"))
        assert keys == {"tx1": "wa:M1:a", "tx2": None, "tx3": "wa:M2:b"}
        assert sorted(r[0] for r in conn.execute("SELECT id FROM finance_budgets")) == ["b1", "b3"]
        assert {r[0] for r in conn.execute("SELECT category_id FROM finance_budgets")} == {"cat-keep"}
        # Guard aktif: duplikat baru ditolak oleh database.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO finance_categories (id, owner_jid, name, category_type, is_default, created_at) "
                "VALUES ('x', ?, 'Makanan', 'expense', 0, ?)",
                (owner, now),
            )
    finally:
        conn.close()
