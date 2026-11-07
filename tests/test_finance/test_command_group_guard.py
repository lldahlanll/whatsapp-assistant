"""!finance command must not expose personal finance data in group chats."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.handlers.finance import FinanceCommandHandler
from whatsapp_platform.features.finance.service import InsufficientBalanceError

GROUP_JID = JID.create_group("120363000000000000")


def _ctx(args: list[str], chat_jid: JID = GROUP_JID) -> MagicMock:
    ctx = MagicMock()
    ctx.message.sender_jid = "628123456789@s.whatsapp.net"
    ctx.message.chat_jid = chat_jid
    ctx.command.args = args
    ctx.reply = AsyncMock()
    return ctx


@pytest.mark.parametrize(
    "args",
    [["saldo"], ["riwayat"], ["laporan"], ["rekening"], ["budget"], ["kategori"], ["reset", "YA"]],
)
async def test_private_subcommands_blocked_in_group(args: list[str]) -> None:
    svc = AsyncMock()
    handler = FinanceCommandHandler(svc)
    ctx = _ctx(args)

    await handler.handle(ctx)

    reply = ctx.reply.call_args[0][0]
    assert "chat pribadi" in reply
    svc.get_total_balance.assert_not_called()
    svc.get_recent_transactions.assert_not_called()
    svc.reset_all_data.assert_not_called()


async def test_insufficient_balance_in_group_hides_amount() -> None:
    svc = AsyncMock()
    svc.get_accounts.return_value = []
    svc.add_expense.side_effect = InsufficientBalanceError(
        "Saldo BCA Rp 12,345, sedangkan transaksi Rp 50,000. Kurang Rp 37,655."
    )
    handler = FinanceCommandHandler(svc)
    ctx = _ctx(["keluar", "50rb", "makan"])

    await handler.handle(ctx)

    svc.add_expense.assert_awaited_once()
    assert svc.add_expense.call_args.kwargs["amount"] == Decimal("50000")
    reply = ctx.reply.call_args[0][0]
    assert "12,345" not in reply
    assert "tidak mencukupi" in reply


async def test_private_chat_still_shows_balance() -> None:
    svc = AsyncMock()
    svc.get_total_balance.return_value = {
        "total": Decimal("100000"),
        "available_balance": Decimal("100000"),
        "investment_balance": Decimal("0"),
        "currency": "IDR",
        "accounts": [],
    }
    handler = FinanceCommandHandler(svc)
    ctx = _ctx(["saldo"], chat_jid=JID(user="628123456789", server="s.whatsapp.net"))

    await handler.handle(ctx)

    svc.get_total_balance.assert_awaited_once()
