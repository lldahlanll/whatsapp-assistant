"""Regression tests for the five medium-priority finance audit fixes.

1. Destructive AI actions need a confirmation from a later user message.
2. Account names match exactly or by whole word; ambiguity is reported.
3. Deactivated accounts can no longer be used.
4. Reversal rows cannot be reversed, edited or deleted.
5. Duplicate processing of the same WhatsApp message records a transaction once.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.handlers.finance import FinanceCommandHandler
from whatsapp_platform.features.finance.service import (
    AccountNotFoundError,
    AccountRequiredError,
    FinanceService,
    ReversalTransactionError,
)
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)
from whatsapp_platform.infrastructure.finance import tool_executor as executor_module
from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor

OWNER = JID.parse("628123456789@s.whatsapp.net")


@pytest.fixture
async def svc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = SQLAlchemyFinanceRepository(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    yield FinanceService(repo)
    await engine.dispose()


async def _call(executor: FinanceToolExecutor, tool: str, args: dict, message_id: str | None) -> dict:
    raw = await executor.execute(tool_name=tool, arguments=args, user_jid=OWNER, chat_jid=OWNER, message_id=message_id)
    return json.loads(raw)


async def _balance(svc: FinanceService, name: str) -> Decimal:
    acc = await svc.find_account_by_name(str(OWNER), name)
    assert acc is not None
    return acc.balance


# ── 1. Server-side confirmation ─────────────────────────────────────────────


async def test_llm_cannot_confirm_reset_in_same_message(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    first = await _call(executor, "finance_reset_data", {"confirm": False}, "msg-1")
    again = await _call(executor, "finance_reset_data", {"confirm": True}, "msg-1")

    assert first["status"] == "preview"
    assert again["status"] == "preview"
    assert len(await svc.get_accounts(str(OWNER))) == 1


async def test_reset_runs_after_user_confirms_in_next_message(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    await _call(executor, "finance_reset_data", {}, "msg-1")
    done = await _call(executor, "finance_reset_data", {"confirm": True}, "msg-2")

    assert done["status"] == "success"
    assert await svc._repo.get_accounts(str(OWNER)) == []


@pytest.mark.parametrize("confirm", ["false", "no", 0, None])
async def test_falsy_confirm_strings_do_not_confirm(svc: FinanceService, confirm) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    await _call(executor, "finance_delete_account", {"name": "BCA"}, "msg-1")
    result = await _call(executor, "finance_delete_account", {"name": "BCA", "confirm": confirm}, "msg-2")

    assert result["status"] == "need_confirmation"


async def test_confirmation_expires(svc: FinanceService, monkeypatch: pytest.MonkeyPatch) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)
    monkeypatch.setattr(executor_module, "_CONFIRMATION_TTL_SECONDS", -1.0)

    await _call(executor, "finance_delete_account", {"name": "BCA"}, "msg-1")
    result = await _call(executor, "finance_delete_account", {"name": "BCA", "confirm": True}, "msg-2")

    assert result["status"] == "need_confirmation"


async def test_without_message_id_destructive_action_never_runs(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    for _ in range(2):
        result = await _call(executor, "finance_delete_account", {"name": "BCA", "confirm": True}, None)
        assert result["status"] == "need_confirmation"


async def test_delete_transaction_needs_confirmation_from_next_message(svc: FinanceService) -> None:
    bca = await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(str(OWNER), Decimal("25000"), account_id=bca.id, description="kopi")
    executor = FinanceToolExecutor(svc)

    first = await _call(executor, "finance_delete_transaction", {"transaction_id": tx.id, "confirm": True}, "msg-1")
    assert first["status"] == "need_confirmation"
    assert await _balance(svc, "BCA") == Decimal("75000")

    done = await _call(executor, "finance_delete_transaction", {"transaction_id": tx.id, "confirm": True}, "msg-2")
    assert done["status"] == "success"
    assert await _balance(svc, "BCA") == Decimal("100000")


async def test_confirmation_is_bound_to_the_previewed_transaction(svc: FinanceService) -> None:
    bca = await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    kopi = await svc.add_expense(str(OWNER), Decimal("25000"), account_id=bca.id, description="kopi")
    roti = await svc.add_expense(str(OWNER), Decimal("10000"), account_id=bca.id, description="roti")
    executor = FinanceToolExecutor(svc)

    await _call(executor, "finance_delete_transaction", {"transaction_id": kopi.id}, "msg-1")
    other = await _call(executor, "finance_delete_transaction", {"transaction_id": roti.id, "confirm": True}, "msg-2")

    assert other["status"] == "need_confirmation"
    assert await _balance(svc, "BCA") == Decimal("65000")


# ── 2. Account name matching ────────────────────────────────────────────────


async def test_exact_name_wins_over_partial(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA Tabungan", AccountType.SAVINGS)
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK)

    assert (await svc.find_account_by_name(str(OWNER), "bca")).name == "BCA"
    assert (await svc.find_account_by_name(str(OWNER), "tabungan")).name == "BCA Tabungan"
    assert (await svc.find_account_by_name(str(OWNER), "dari rekening BCA")).name == "BCA"


async def test_ambiguous_name_asks_user(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA Tabungan", AccountType.SAVINGS)
    await svc.create_account(str(OWNER), "BCA Bisnis", AccountType.BANK)

    with pytest.raises(AccountRequiredError, match="BCA Tabungan"):
        await svc.find_account_by_name(str(OWNER), "BCA")


async def test_single_letter_does_not_match_everything(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK)

    assert await svc.find_account_by_name(str(OWNER), "a") is None


# ── 3. Deactivated accounts ─────────────────────────────────────────────────


async def test_deleted_account_cannot_be_used(svc: FinanceService) -> None:
    bca = await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    gopay = await svc.create_account(str(OWNER), "GoPay", AccountType.EWALLET, Decimal("50000"))
    await svc.delete_account(str(OWNER), bca.id)

    with pytest.raises(AccountNotFoundError):
        await svc.add_expense(str(OWNER), Decimal("10000"), account_id=bca.id)
    with pytest.raises(AccountNotFoundError):
        await svc.transfer(str(OWNER), Decimal("10000"), from_account_id=gopay.id, to_account_id=bca.id)
    assert await _balance(svc, "GoPay") == Decimal("50000")


# ── 4. Reversal rows are immutable ──────────────────────────────────────────


async def test_reversal_row_cannot_be_reversed_or_deleted(svc: FinanceService) -> None:
    bca = await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    tx = await svc.add_expense(str(OWNER), Decimal("40000"), account_id=bca.id)
    reversal = await svc.reverse_transaction(str(OWNER), tx.id)

    with pytest.raises(ReversalTransactionError):
        await svc.reverse_transaction(str(OWNER), reversal.id)
    with pytest.raises(ReversalTransactionError):
        await svc.delete_transaction(str(OWNER), reversal.id)
    with pytest.raises(ReversalTransactionError):
        await svc.correct_transaction(str(OWNER), reversal.id, new_amount=Decimal("1000"))

    assert await _balance(svc, "BCA") == Decimal("100000")


# ── 5. Idempotency from the WhatsApp message ID ─────────────────────────────


async def test_same_message_processed_twice_records_once(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)
    args = {"amount": 25000, "description": "makan siang", "account_name": "BCA"}

    await _call(executor, "finance_add_expense", args, "wa-msg-1")
    await _call(executor, "finance_add_expense", args, "wa-msg-1")

    assert await _balance(svc, "BCA") == Decimal("75000")
    assert len(await svc.get_recent_transactions(str(OWNER))) == 1


async def test_two_items_in_one_message_are_both_recorded(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    await _call(executor, "finance_add_expense", {"amount": 20000, "description": "kopi", "account_name": "BCA"}, "m")
    await _call(executor, "finance_add_expense", {"amount": 15000, "description": "roti", "account_name": "BCA"}, "m")

    assert await _balance(svc, "BCA") == Decimal("65000")


async def test_llm_supplied_idempotency_key_is_ignored(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "BCA", AccountType.BANK, Decimal("100000"))
    executor = FinanceToolExecutor(svc)

    # LLM reuses a stale key for a genuinely new transaction in a new message
    await _call(executor, "finance_add_expense", {"amount": 10000, "account_name": "BCA", "idempotency_key": "x"}, "m1")
    await _call(executor, "finance_add_expense", {"amount": 10000, "account_name": "BCA", "idempotency_key": "x"}, "m2")

    assert await _balance(svc, "BCA") == Decimal("80000")


async def test_duplicate_command_event_records_once(svc: FinanceService) -> None:
    await svc.create_account(str(OWNER), "Kas", AccountType.CASH, Decimal("100000"))
    handler = FinanceCommandHandler(svc)

    for _ in range(2):
        ctx = MagicMock()
        ctx.message.id = "3EB0DUPLICATE"
        ctx.message.sender_jid = OWNER
        ctx.message.chat_jid = OWNER
        ctx.message.timestamp = datetime.now(UTC)
        ctx.command.args = ["keluar", "30rb", "bensin"]
        ctx.reply = AsyncMock()
        await handler.handle(ctx)

    assert await _balance(svc, "Kas") == Decimal("70000")
