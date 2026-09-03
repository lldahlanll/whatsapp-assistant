"""Unit tests for CustomerLookupRepository using mock aiomysql pool."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.customer_lookup.repository import (
    CustomerLookupRepository,
    CustomerLookupUnavailableError,
)


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = MagicMock()
    cursor = AsyncMock()

    # Async context manager mock for pool.acquire()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Async context manager mock for conn.cursor()
    conn.cursor.return_value.__aenter__ = AsyncMock(return_value=cursor)
    conn.cursor.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


@pytest.mark.asyncio
async def test_find_by_phone_suffix_success(mock_pool: MagicMock) -> None:
    settings = Settings(mysql_query_timeout_ms=3000)
    repo = CustomerLookupRepository(settings=settings, pool=mock_pool)

    # Get the mock cursor reference
    cursor = mock_pool.acquire.return_value.__aenter__.return_value.cursor.return_value.__aenter__.return_value
    now = datetime(2026, 5, 13, 10, 0)
    cursor.fetchall.return_value = [("CUST-001", "08123456789", "JOKO", now)]

    records = await repo.find_by_phone_suffix("8123456789")

    assert len(records) == 1
    assert records[0].kode_kustomer == "CUST-001"
    assert records[0].no_hp == "08123456789"
    assert records[0].add_user == "JOKO"
    assert records[0].add_date == now

    # Verify query statements
    calls = cursor.execute.call_args_list
    assert len(calls) == 2
    # First call: set session timeout
    assert calls[0][0][0] == "SET SESSION MAX_EXECUTION_TIME = 3000"
    # Second call: parameterized query
    sql, params = calls[1][0]
    assert "SELECT `Kode_kustomer`, `No_hp`, `Add_user`, `AddDate`" in sql
    assert "FROM `kustomer_temp`" in sql
    assert "WHERE `No_hp` LIKE %s" in sql
    assert params == ("%8123456789",)


@pytest.mark.asyncio
async def test_find_by_phone_suffix_raises_unavailable_error_on_db_failure(
    mock_pool: MagicMock,
) -> None:
    settings = Settings(mysql_query_timeout_ms=3000)
    repo = CustomerLookupRepository(settings=settings, pool=mock_pool)

    mock_pool.acquire.side_effect = RuntimeError("MySQL Connection Refused")

    with pytest.raises(CustomerLookupUnavailableError) as exc_info:
        await repo.find_by_phone_suffix("8123456789")

    assert "MySQL connection or query failure" in str(exc_info.value)
