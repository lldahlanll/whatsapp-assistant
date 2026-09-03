"""MySQL Customer Lookup Repository implementation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from whatsapp_platform.infrastructure.customer_lookup.models import CustomerRecord
from whatsapp_platform.infrastructure.customer_lookup.mysql_pool import get_pool

if TYPE_CHECKING:
    import aiomysql

    from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


class CustomerLookupUnavailableError(Exception):
    """Raised when MySQL database query fails or times out."""


class CustomerLookupRepository:
    """Read-only repository for looking up customer records from MySQL database."""

    def __init__(self, settings: Settings, pool: aiomysql.Pool | None = None) -> None:
        self._settings = settings
        self._pool = pool

    async def _get_active_pool(self) -> aiomysql.Pool:
        if self._pool is not None:
            return self._pool
        return await get_pool(self._settings)

    async def find_by_phone_suffix(self, phone_core: str) -> list[CustomerRecord]:
        """Find up to 5 matching customer records by phone core suffix.

        Args:
            phone_core: Normalized phone core digits (e.g. "8123456789")

        Returns:
            List of matching CustomerRecord objects (empty if no matches).

        Raises:
            CustomerLookupUnavailableError: On connection failure, SQL error, or timeout.
        """
        timeout_seconds = (self._settings.mysql_query_timeout_ms / 1000.0) + 0.5

        try:
            return await asyncio.wait_for(
                self._execute_query(phone_core),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            logger.warning(
                "Customer lookup query timed out",
                phone_core_masked=f"{phone_core[:3]}***{phone_core[-2:]}"
                if len(phone_core) >= 5
                else "***",
                timeout_ms=self._settings.mysql_query_timeout_ms,
            )
            raise CustomerLookupUnavailableError("Customer lookup query timed out") from exc
        except CustomerLookupUnavailableError:
            raise
        except Exception as exc:
            logger.error(
                "Customer lookup query failed",
                error=str(exc),
                exc_info=True,
            )
            raise CustomerLookupUnavailableError("MySQL connection or query failure") from exc

    async def _execute_query(self, phone_core: str) -> list[CustomerRecord]:
        pool = await self._get_active_pool()
        param = f"%{phone_core}"
        timeout_ms = int(self._settings.mysql_query_timeout_ms)

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {timeout_ms}")
                except Exception as exc:
                    logger.debug("Failed to set session max execution time", error=str(exc))

                sql = (
                    "SELECT `Kode_kustomer`, `No_hp`, `Add_user`, `AddDate` "
                    "FROM `kustomer_temp` "
                    "WHERE `No_hp` LIKE %s "
                    "ORDER BY `AddDate` DESC "
                    "LIMIT 5;"
                )
                await cur.execute(sql, (param,))
                rows = await cur.fetchall()

                records: list[CustomerRecord] = []
                for row in rows:
                    kode_kustomer = str(row[0]) if row[0] is not None else ""
                    no_hp = str(row[1]) if row[1] is not None else ""
                    add_user = str(row[2]) if row[2] is not None else ""
                    add_date = row[3] if isinstance(row[3], datetime) else datetime.now(UTC)
                    records.append(
                        CustomerRecord(
                            kode_kustomer=kode_kustomer,
                            no_hp=no_hp,
                            add_user=add_user,
                            add_date=add_date,
                        )
                    )
                return records
