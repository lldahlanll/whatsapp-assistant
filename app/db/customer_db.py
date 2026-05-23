# app/db/customer_db.py
"""
Read-only async connection pool untuk database customer kantor.

Design rules:
- Pool size kecil (5) — query jarang, no need over-provision
- Statement timeout di-enforce per-connection di sisi server (MAX_EXECUTION_TIME)
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
        Acquire connection + DictCursor dengan server-side statement timeout.

        MAX_EXECUTION_TIME (MySQL 5.7.8+) membatasi durasi SELECT di SISI SERVER.
        Ini berbeda dari asyncio.wait_for yang hanya membatalkan di sisi Python —
        tanpa ini, query lambat tetap jalan di MySQL meski Python sudah timeout.
        """
        if self._pool is None:
            await self.init()
        if self._pool is None:
            raise RuntimeError("CustomerDB pool not available")

        # Konversi detik → milidetik untuk MAX_EXECUTION_TIME
        timeout_ms = int(settings.customer_db_query_timeout * 1000)

        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Set per-session. autocommit=True jadi langsung efektif.
                # Hanya berlaku untuk SELECT (sesuai desain read-only kita).
                try:
                    await cur.execute(
                        "SET SESSION MAX_EXECUTION_TIME = %s", (timeout_ms,)
                    )
                except aiomysql.Error as e:
                    # MariaDB tidak punya MAX_EXECUTION_TIME (pakai max_statement_time
                    # dalam detik). Kalau gagal, log tapi jangan crash —
                    # asyncio.wait_for di fetch_all tetap jadi safety net.
                    logger.warning(
                        f"[CustomerDB] Gagal set MAX_EXECUTION_TIME "
                        f"(server mungkin MariaDB?): {e}"
                    )
                yield cur

    async def fetch_all(
        self,
        sql: str,
        params: tuple | dict | None = None,
        timeout: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Run parameterized SELECT, return list of dicts.

        Dua lapis proteksi timeout:
        1. MAX_EXECUTION_TIME (server-side) — hentikan query di MySQL
        2. asyncio.wait_for (client-side) — bebaskan coroutine Python

        Args:
            sql: query dengan %s placeholders (aiomysql convention)
            params: tuple/dict untuk binding
            timeout: override default timeout (detik) untuk lapis client-side
        """
        timeout = timeout or settings.customer_db_query_timeout

        try:
            async with self.cursor() as cur:
                await asyncio.wait_for(
                    cur.execute(sql, params),
                    timeout=timeout + 1.0,  # beri server-side timeout kesempatan duluan
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