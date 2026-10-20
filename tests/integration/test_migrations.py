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
