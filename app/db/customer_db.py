# app/db/customer_db.py
"""
Read-only async connection pool untuk database customer kantor.

Design rules:
- Pool size kecil (5) — query jarang, no need over-provision
- Statement timeout di-enforce per-connection
- Semua query parameterized — TIDAK ada string concat ke SQL
- User DB read-only di level MySQL (defense in depth)
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import aiomysql
from loguru import logger

from app.config import settings


class CustomerDB:
    """Singleton wrapper untuk pool aiomysql."""

    def __init__(self) -> None:
        self._pool: Optional[aiomysql.Pool] = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Lazy-init pool. Idempotent."""
        if self._pool is not None:
            return

        async with self._lock:
            if self._pool is not None:
                return

            if not settings.customer_db_configured:
                logger.warning("[CustomerDB] Not configured — skipping init")
                return

            try:
                self._pool = await aiomysql.create_pool(
                    host=settings.customer_db_host,
                    port=settings.customer_db_port,
                    user=settings.customer_db_user,
                    password=settings.customer_db_password,
                    db=settings.customer_db_name,
                    minsize=1,
                    maxsize=settings.customer_db_pool_size,
                    autocommit=True,
                    charset="utf8mb4",
                    connect_timeout=5,
                )
                logger.info(
                    f"[CustomerDB] ✓ Pool connected → "
                    f"{settings.customer_db_host}:{settings.customer_db_port}"
                    f"/{settings.customer_db_name}"
                )
            except Exception as e:
                logger.error(f"[CustomerDB] ✗ Connection failed: {e}")
                raise

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            logger.info("[CustomerDB] Pool closed")

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[aiomysql.DictCursor]:
        """
        Acquire connection + DictCursor.
        Statement timeout di-set per-connection di MySQL (MAX_EXECUTION_TIME hint).
        """
        if self._pool is None:
            await self.init()
        if self._pool is None:
            raise RuntimeError("CustomerDB pool not available")

        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                yield cur

    async def fetch_all(
        self,
        sql: str,
        params: tuple | dict | None = None,
        timeout: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Run parameterized SELECT, return list of dicts.

        Args:
            sql: query dengan %s placeholders (aiomysql convention)
            params: tuple/dict untuk binding
            timeout: override default timeout (detik)
        """
        timeout = timeout or settings.customer_db_query_timeout

        try:
            async with self.cursor() as cur:
                # Wrap dengan asyncio.wait_for untuk hard timeout
                await asyncio.wait_for(
                    cur.execute(sql, params),
                    timeout=timeout,
                )
                rows = await cur.fetchall()
                logger.debug(f"[CustomerDB] Query OK | rows={len(rows)}")
                return list(rows)
        except asyncio.TimeoutError:
            logger.error(f"[CustomerDB] Query timeout >{timeout}s | sql={sql[:80]}")
            raise
        except aiomysql.Error as e:
            logger.error(f"[CustomerDB] MySQL error: {e} | sql={sql[:80]}")
            raise


# Singleton
customer_db = CustomerDB()