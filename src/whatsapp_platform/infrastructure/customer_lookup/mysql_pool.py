"""Async MySQL connection pool management using aiomysql."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiomysql
import structlog

if TYPE_CHECKING:
    from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()

_pool: aiomysql.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool(settings: Settings | None = None) -> aiomysql.Pool:
    """Get lazy-initialized singleton aiomysql Pool."""
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        if settings is None:
            raise RuntimeError(
                "Settings must be provided when initializing MySQL pool for the first time"
            )

        try:
            logger.info(
                "Initializing MySQL connection pool",
                host=settings.mysql_host,
                port=settings.mysql_port,
                db=settings.mysql_db,
                min_size=settings.mysql_pool_min_size,
                max_size=settings.mysql_pool_max_size,
            )
            _pool = await aiomysql.create_pool(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                db=settings.mysql_db,
                minsize=settings.mysql_pool_min_size,
                maxsize=settings.mysql_pool_max_size,
                autocommit=True,
            )
            return _pool
        except Exception as exc:
            logger.error(
                "Failed to create MySQL connection pool",
                error=str(exc),
                host=settings.mysql_host,
                port=settings.mysql_port,
            )
            raise


async def close_pool() -> None:
    """Close MySQL connection pool gracefully if active."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            logger.info("Closing MySQL connection pool")
            _pool.close()
            await _pool.wait_closed()
            _pool = None
            logger.info("MySQL connection pool closed")
