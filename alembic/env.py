"""Alembic async-compatible environment configuration.

Reads database URL from Settings (environment variables), not alembic.ini.
Supports SQLAlchemy 2.0 async engine (required for aiosqlite).
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# ---------------------------------------------------------------------------
# Path setup: ensure src/ is importable
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

# ---------------------------------------------------------------------------
# Import project modules AFTER sys.path is set
# ---------------------------------------------------------------------------
# Import all models so Alembic can detect them for autogenerate
import whatsapp_platform.infrastructure.database.models  # noqa: E402, F401
from whatsapp_platform.infrastructure.config.settings import Settings  # noqa: E402
from whatsapp_platform.infrastructure.database.base import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Load database URL from environment / Settings."""
    settings = Settings()
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed).

    Useful for generating SQL scripts without a running database.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with live DB connection)."""
    url = get_database_url()
    connectable = create_async_engine(url, echo=False, future=True)

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn,
                target_metadata=target_metadata,
                render_as_batch=True,  # Required for SQLite ALTER TABLE support
                compare_type=True,
            )
        )
        await connection.run_sync(lambda _: context.run_migrations())

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
