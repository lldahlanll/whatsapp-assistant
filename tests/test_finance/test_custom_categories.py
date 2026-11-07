"""Kategori buatan user: tambah, hapus, dipakai di transaksi & budget, dan routing tool AI."""

import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import AccountType, CategoryType
from whatsapp_platform.features.finance.service import (
    MAX_CUSTOM_CATEGORIES,
    CategoryAlreadyExistsError,
    CategoryInUseError,
    CategoryNotFoundError,
    FinanceService,
    FinanceServiceError,
)
from whatsapp_platform.infrastructure.ai.finance_fast_path import try_finance_mutation_fast_path
from whatsapp_platform.infrastructure.ai.tool_policy import _select_finance_tools
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
)
from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor

OWNER = "user1@s.whatsapp.net"


@pytest.fixture
async def svc():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = FinanceService(SQLAlchemyFinanceRepository(factory))
    await service.create_account(OWNER, "Dompet", AccountType.CASH, Decimal("1000000"))
    yield service
    await engine.dispose()


async def test_create_expense_and_income_category(svc):
    kopi = await svc.create_category(OWNER, "  Kopi  ", "pengeluaran", icon="☕")
    kos = await svc.create_category(OWNER, "Sewa Kos", "income")

    assert (kopi.name, kopi.category_type, kopi.icon, kopi.is_default) == (
        "Kopi", CategoryType.EXPENSE, "☕", False,
    )
    assert kos.category_type == CategoryType.INCOME
    assert kos.icon  # ikon default diisi
    names = {c.name for c in await svc.get_categories(OWNER, "expense")}
    assert "Kopi" in names and "Makanan & Minuman" in names


async def test_duplicate_name_rejected_case_insensitive(svc):
    await svc.create_category(OWNER, "Kopi", "expense")
    with pytest.raises(CategoryAlreadyExistsError):
        await svc.create_category(OWNER, "KOPI", "expense")
    with pytest.raises(CategoryAlreadyExistsError):
        await svc.create_category(OWNER, "transport", "expense")  # bentrok dengan default
    # Nama sama di tipe berbeda boleh.
    await svc.create_category(OWNER, "Kopi", "income")


async def test_invalid_input_rejected(svc):
    with pytest.raises(FinanceServiceError):
        await svc.create_category(OWNER, "K", "expense")
    with pytest.raises(FinanceServiceError):
        await svc.create_category(OWNER, "x" * 41, "expense")
    with pytest.raises(FinanceServiceError):
        await svc.create_category(OWNER, "Kopi", "tabungan")


async def test_custom_category_limit(svc):
    for i in range(MAX_CUSTOM_CATEGORIES):
        await svc.create_category(OWNER, f"Kat {i}", "expense")
    with pytest.raises(FinanceServiceError, match="Batas"):
        await svc.create_category(OWNER, "Satu Lagi", "expense")


async def test_budget_on_custom_category(svc):
    await svc.create_category(OWNER, "Skincare", "expense")
    progress = await svc.set_budget(OWNER, "skincare", Decimal("300000"))
    assert progress.budget.category_name == "Skincare"

    await svc.add_expense(OWNER, Decimal("100000"), description="serum", category_name="Skincare")
    progress = await svc.get_budget_progress(OWNER, "Skincare")
    assert progress.spent == Decimal("100000")


async def test_budget_unknown_category_suggests_creating(svc):
    with pytest.raises(CategoryNotFoundError, match="Buat dulu"):
        await svc.set_budget(OWNER, "Skincare", Decimal("300000"))


async def test_budget_never_resolves_to_income_category(svc):
    # "Gaji" hanya ada sebagai kategori pemasukan -> tidak boleh dipakai untuk budget.
    with pytest.raises(CategoryNotFoundError):
        await svc.set_budget(OWNER, "Gaji", Decimal("100000"))


async def test_auto_category_prefers_custom_over_keyword(svc):
    await svc.create_category(OWNER, "Kopi", "expense")
    tx = await svc.add_expense(OWNER, Decimal("25000"), description="beli kopi susu")
    assert tx.category_name == "Kopi"  # bukan "Makanan & Minuman" dari keyword map


async def test_explicit_category_matches_transaction_type(svc):
    # "Investasi" ada di pemasukan & pengeluaran; pemasukan harus dapat yang pemasukan.
    tx = await svc.add_income(OWNER, Decimal("50000"), description="dividen", category_name="Investasi")
    cats = {c.id: c for c in await svc.get_categories(OWNER)}
    assert cats[tx.category_id].category_type == CategoryType.INCOME


async def test_delete_category_rules(svc):
    await svc.create_category(OWNER, "Kopi", "expense")
    deleted = await svc.delete_category(OWNER, "kopi")
    assert deleted.name == "Kopi"
    assert "Kopi" not in {c.name for c in await svc.get_categories(OWNER)}

    with pytest.raises(FinanceServiceError, match="default"):
        await svc.delete_category(OWNER, "Transport")
    with pytest.raises(CategoryNotFoundError):
        await svc.delete_category(OWNER, "Tidak Ada")

    await svc.create_category(OWNER, "Skincare", "expense")
    await svc.set_budget(OWNER, "Skincare", Decimal("100000"))
    with pytest.raises(CategoryInUseError, match="1 budget"):
        await svc.delete_category(OWNER, "Skincare")

    await svc.create_category(OWNER, "Parfum", "expense")
    await svc.add_expense(OWNER, Decimal("10000"), category_name="Parfum")
    with pytest.raises(CategoryInUseError, match="1 transaksi"):
        await svc.delete_category(OWNER, "Parfum")


async def test_delete_ambiguous_name_needs_type(svc):
    await svc.create_category(OWNER, "Arisan", "expense")
    await svc.create_category(OWNER, "Arisan", "income")
    with pytest.raises(FinanceServiceError, match="Sebutkan tipenya"):
        await svc.delete_category(OWNER, "Arisan")
    deleted = await svc.delete_category(OWNER, "Arisan", "pemasukan")
    assert deleted.category_type == CategoryType.INCOME


async def test_deleted_category_lands_in_audit_log(svc):
    await svc.create_category(OWNER, "Kopi", "expense")
    await svc.delete_category(OWNER, "Kopi")
    entries = await svc.get_audit_log(OWNER)
    assert any(e.entity_type == "category" and e.snapshot.get("name") == "Kopi" for e in entries)


async def test_tool_executor_create_and_delete(svc):
    executor = FinanceToolExecutor(svc)
    out = json.loads(await executor.execute(
        "finance_create_category", {"name": "Kopi", "category_type": "expense"}, OWNER, OWNER,
    ))
    assert out["status"] == "success" and out["category"] == "Kopi"

    dup = json.loads(await executor.execute(
        "finance_create_category", {"name": "kopi"}, OWNER, OWNER,
    ))
    assert dup["error_code"] == "CATEGORY_EXISTS"

    out = json.loads(await executor.execute("finance_delete_category", {"name": "Kopi"}, OWNER, OWNER))
    assert out["status"] == "success"


async def test_tool_executor_blocks_category_tools_in_group(svc):
    executor = FinanceToolExecutor(svc)
    out = json.loads(await executor.execute(
        "finance_create_category", {"name": "Kopi"}, OWNER, "123@g.us",
    ))
    assert out["error_code"] == "GROUP_PRIVATE_ONLY"


def test_create_category_has_no_fast_path_so_llm_can_chain_budget():
    raw = json.dumps({"status": "success", "category": "Kopi", "category_type": "expense"})
    assert try_finance_mutation_fast_path("finance_create_category", raw) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("tambah kategori pengeluaran kopi", "finance_create_category"),
        ("bikin kategori baru skincare", "finance_create_category"),
        ("hapus kategori kopi", "finance_delete_category"),
        ("buat kategori kopi terus budget 200rb", "finance_create_budget"),
        ("budget skincare 300rb", "finance_create_category"),
        ("iya", "finance_create_category"),
    ],
)
def test_tool_routing(text, expected):
    names = {t.name for t in _select_finance_tools(text)}
    assert expected in names
