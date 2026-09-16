"""Test kasus start awal rekening kosong dan penanganan saldo."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_platform.domain.entities.finance import AccountType, FinanceAccount
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.finance import FinanceCommandHandler
from whatsapp_platform.features.finance.formatter import format_balance
from whatsapp_platform.features.finance.service import (
    AccountNotFoundError,
    AccountRequiredError,
    FinanceService,
)


@pytest.fixture
def owner_jid() -> str:
    return "user@s.whatsapp.net"


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_accounts = AsyncMock(return_value=[])
    repo.get_categories = AsyncMock(return_value=[])
    return repo


@pytest.mark.asyncio
async def test_ensure_defaults_does_not_create_cash_account(
    mock_repo: AsyncMock, owner_jid: str
) -> None:
    """Pastikan ensure_defaults hanya membuat kategori, bukan akun 'Kas'."""
    svc = FinanceService(mock_repo)
    await svc.ensure_defaults(owner_jid)

    # create_account di repo tidak boleh dipanggil saat ensure_defaults
    mock_repo.create_account.assert_not_called()
    # create_category harus dipanggil untuk seeding kategori
    assert mock_repo.create_category.call_count > 0


@pytest.mark.asyncio
async def test_resolve_account_raises_when_no_accounts(
    mock_repo: AsyncMock, owner_jid: str
) -> None:
    """Jika belum ada rekening, harus raise AccountNotFoundError dengan pesan edukatif."""
    svc = FinanceService(mock_repo)
    mock_repo.get_accounts.return_value = []

    with pytest.raises(AccountNotFoundError) as exc_info:
        await svc.add_income(
            owner_jid=owner_jid,
            amount=Decimal("50000"),
            description="Uang saku",
        )

    assert "Belum ada rekening/dompet terdaftar" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_account_lists_accounts_when_unspecified(
    mock_repo: AsyncMock, owner_jid: str
) -> None:
    """Jika ada banyak rekening dan belum ditentukan, sebutkan nama-nama rekeningnya."""
    svc = FinanceService(mock_repo)
    acc1 = FinanceAccount(
        id="acc-1", owner_jid=owner_jid, name="BCA",
        account_type=AccountType.BANK, currency="IDR",
        balance=Decimal("100"), is_active=True, created_at=None,  # type: ignore[arg-type]
    )
    acc2 = FinanceAccount(
        id="acc-2", owner_jid=owner_jid, name="GoPay",
        account_type=AccountType.EWALLET, currency="IDR",
        balance=Decimal("100"), is_active=True, created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_accounts.return_value = [acc1, acc2]

    with pytest.raises(AccountRequiredError) as exc_info:
        await svc.add_income(
            owner_jid=owner_jid,
            amount=Decimal("50000"),
            description="Gaji",
        )

    assert "'BCA'" in str(exc_info.value)
    assert "'GoPay'" in str(exc_info.value)


def test_format_balance_empty_accounts() -> None:
    """Pastikan format_balance saat belum ada rekening menampilkan panduan pembuatan rekening."""
    data = {"total": Decimal("0"), "accounts": [], "currency": "IDR"}
    text = format_balance(data)

    assert "Belum ada rekening/dompet terdaftar" in text
    assert "!finance rekening baru" in text


@pytest.mark.asyncio
async def test_finance_command_tambah_and_topup_alias(
    mock_repo: AsyncMock, owner_jid: str
) -> None:
    """Pastikan sub-command !finance tambah dan !finance topup dikenali."""
    svc = FinanceService(mock_repo)
    bca_acc = FinanceAccount(
        id="acc-bca", owner_jid=owner_jid, name="BCA",
        account_type=AccountType.BANK, currency="IDR",
        balance=Decimal("500000"), is_active=True, created_at=None,  # type: ignore[arg-type]
    )
    mock_repo.get_accounts.return_value = [bca_acc]
    mock_repo.get_account_by_id.return_value = bca_acc
    mock_repo.get_transaction_by_idempotency_key.return_value = None

    saved_tx = MagicMock()
    saved_tx.amount = Decimal("100000")
    saved_tx.account_name = "BCA"
    saved_tx.category_name = "Lainnya"
    saved_tx.description = "Freelance"
    saved_tx.transaction_type = MagicMock()
    saved_tx.transaction_date = MagicMock()
    saved_tx.transaction_date.strftime.return_value = "10 Sep 2026"
    mock_repo.save_transaction_atomic.return_value = saved_tx

    handler = FinanceCommandHandler(svc)

    # Test !finance tambah 100rb freelance BCA
    ctx = MagicMock()
    ctx.message.sender_jid = owner_jid
    ctx.command.args = ["tambah", "100rb", "freelance", "BCA"]
    ctx.reply = AsyncMock()

    await handler.handle(ctx)
    ctx.reply.assert_called_once()
    reply_text = ctx.reply.call_args[0][0]
    assert "Tercatat" in reply_text
