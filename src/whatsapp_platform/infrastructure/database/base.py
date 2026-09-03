"""SQLAlchemy Async engine and session setup."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def create_engine_and_session_factory(db_url: str):
    # Ensure local directory exists for SQLite
    if db_url.startswith("sqlite+aiosqlite:///"):
        path_str = db_url.replace("sqlite+aiosqlite:///", "")
        if path_str != ":memory:":
            db_path = Path(path_str)
            db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(db_url, echo=False, future=True)
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, async_session_factory
