"""Backup otomatis database SQLite sebelum Alembic menjalankan migrasi baru.

Dipanggil saat startup: jika ada revisi yang belum diterapkan, salinan konsisten
database (via SQLite backup API, aman untuk mode WAL) disimpan di
``<folder_db>/backups/`` sebelum ``alembic upgrade head`` dijalankan.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url


def sqlite_path_from_url(database_url: str, base_dir: Path) -> Path | None:
    """Kembalikan path file SQLite dari URL SQLAlchemy, atau None jika bukan SQLite berbasis file."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else base_dir / path


def _current_revisions(db_path: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    except sqlite3.OperationalError:
        return set()  # tabel alembic_version belum ada
    finally:
        conn.close()
    return {row[0] for row in rows}


def _head_revisions(project_root: Path) -> set[str]:
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _copy_sqlite(db_path: Path, dest: Path) -> None:
    """Salin konsisten via SQLite backup API (aman saat DB sedang dipakai / mode WAL)."""
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def snapshot_database(database_url: str, project_root: Path, reason: str, keep: int = 10) -> Path | None:
    """Snapshot database sebelum operasi yang tidak bisa dibatalkan (mis. reset data).

    Disimpan di ``<folder_db>/backups/snapshots/``. Mengembalikan path snapshot, atau None jika
    database bukan file SQLite. Exception dilempar jika snapshot gagal agar operasi dibatalkan.
    """
    db_path = sqlite_path_from_url(database_url, project_root)
    if db_path is None or not db_path.exists():
        return None

    snapshot_dir = db_path.parent / "backups" / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "-" for c in reason) or "snapshot"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = snapshot_dir / f"{db_path.stem}-{safe_reason}-{timestamp}.db"
    _copy_sqlite(db_path, path)

    snapshots = sorted(snapshot_dir.glob(f"{db_path.stem}-*.db"), key=lambda p: p.stat().st_mtime)
    for old in snapshots[:-keep] if keep > 0 else []:
        old.unlink()
    return path


def backup_before_migration(database_url: str, project_root: Path, keep: int = 5) -> Path | None:
    """Backup database jika masih ada migrasi tertunda. Mengembalikan path backup atau None."""
    db_path = sqlite_path_from_url(database_url, project_root)
    if db_path is None or not db_path.exists() or db_path.stat().st_size == 0:
        return None

    current = _current_revisions(db_path)
    if current == _head_revisions(project_root):
        return None

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    revision = "-".join(sorted(current)) or "base"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}-{revision}-{timestamp}.db"

    _copy_sqlite(db_path, backup_path)

    # Simpan hanya `keep` backup terbaru untuk database ini.
    backups = sorted(backup_dir.glob(f"{db_path.stem}-*.db"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink()

    return backup_path
