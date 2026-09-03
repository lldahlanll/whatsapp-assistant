"""Unit & Integration tests for Finance Budgeting feature."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from whatsapp_platform.domain.entities.finance import (
    AccountType,
    BudgetProgress,
    FinanceAccount,
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    TransactionType,
)
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.features.commands.context import CommandContext
from whatsapp_platform.features.commands.handlers.finance import FinanceCommandHandler
from whatsapp_platform.features.finance.formatter import (
    format_budget_list,
    format_budget_progress,
)
from whatsapp_platform.features.finance.service import (
    CategoryNotFoundError,
    FinanceService,
    InvalidAmountError,
)
from whatsapp_platform.infrastructure.database.base import Base
from whatsapp_platform.infrastructure.database.repositories.finance_repo import (
    SQLAlchemyFinanceRepository,
    _calculate_budget_status,
)
from whatsapp_platform.infrastructure.finance.tool_executor import FinanceToolExecutor


@pytest.fixture
async def async_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def owner_jid() -> str:
    return "user1@s.whatsapp.net"


@pytest.fixture
def other_owner_jid() -> str:
    return "user2@s.whatsapp.net"


# ── Status Calculation Tests ──────────────────────────────────────────────────


def test_budget_status_thresholds():
    assert _calculate_budget_status(0.0) == "aman"
    assert _calculate_budget_status(50.0) == "aman"
    assert _calculate_budget_status(69.9) == "aman"
    assert _calculate_budget_status(70.0) == "perhatian"
    assert _calculate_budget_status(85.0) == "perhatian"
    assert _calculate_budget_status(89.9) == "perhatian"
    assert _calculate_budget_status(90.0) == "hampir habis"
    assert _calculate_budget_status(99.9) == "hampir habis"
    assert _calculate_budget_status(100.0) == "hampir habis"
    assert _calculate_budget_status(100.1) == "melebihi budget"
    assert _calculate_budget_status(150.0) == "melebihi budget"


# ── Repository & Progress Calculation Tests (Real DB) ─────────────────────────


@pytest.mark.asyncio
async def test_repo_create_and_get_budget(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    cat = await repo.create_category(
        FinanceCategory(
            id="cat-food",
            owner_jid=owner_jid,
            name="Makanan & Minuman",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🍜",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )

    budget = FinanceBudget(
        id="b-1",
        owner_jid=owner_jid,
        category_id=cat.id,
        amount=Decimal("1000000"),
        month=8,
        year=2026,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    created = await repo.upsert_budget(budget)
    assert created.amount == Decimal("1000000")
    assert created.category_name == "Makanan & Minuman"

    fetched = await repo.get_budget(owner_jid, cat.id, 8, 2026)
    assert fetched is not None
    assert fetched.amount == Decimal("1000000")


@pytest.mark.asyncio
async def test_repo_update_existing_budget_upsert(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    cat = await repo.create_category(
        FinanceCategory(
            id="cat-food",
            owner_jid=owner_jid,
            name="Makanan & Minuman",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🍜",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )

    budget1 = FinanceBudget(
        id="b-1",
        owner_jid=owner_jid,
        category_id=cat.id,
        amount=Decimal("1000000"),
        month=8,
        year=2026,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await repo.upsert_budget(budget1)

    # Upsert with new amount
    budget2 = FinanceBudget(
        id="b-2",
        owner_jid=owner_jid,
        category_id=cat.id,
        amount=Decimal("1500000"),
        month=8,
        year=2026,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    updated = await repo.upsert_budget(budget2)
    assert updated.amount == Decimal("1500000")

    budgets = await repo.get_budgets(owner_jid, 8, 2026)
    assert len(budgets) == 1
    assert budgets[0].amount == Decimal("1500000")


@pytest.mark.asyncio
async def test_budget_progress_calculations(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    cat = await repo.create_category(
        FinanceCategory(
            id="cat-food",
            owner_jid=owner_jid,
            name="Makanan & Minuman",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🍜",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )
    acc = await repo.create_account(
        FinanceAccount(
            id="acc-cash",
            owner_jid=owner_jid,
            name="Kas",
            account_type=AccountType.CASH,
            currency="IDR",
            balance=Decimal("2000000"),
            is_active=True,
            created_at=datetime.now(UTC),
        )
    )

    # Budget 1.000.000
    await repo.upsert_budget(
        FinanceBudget(
            id="b-1",
            owner_jid=owner_jid,
            category_id=cat.id,
            amount=Decimal("1000000"),
            month=8,
            year=2026,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    # Add expense of 650.000 on August 2026
    tx = FinanceTransaction(
        id="tx-1",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("650000"),
        category_id=cat.id,
        description="Makan ayam & steak",
        transaction_date=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
    )
    await repo.add_transaction(tx)

    progress = await repo.get_budget_progress(owner_jid, cat.id, 8, 2026)
    assert progress is not None
    assert progress.spent == Decimal("650000")
    assert progress.remaining == Decimal("350000")
    assert progress.percentage == 65.0
    assert progress.status == "aman"


@pytest.mark.asyncio
async def test_over_budget_condition(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    cat = await repo.create_category(
        FinanceCategory(
            id="cat-ent",
            owner_jid=owner_jid,
            name="Hiburan",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🎮",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )
    acc = await repo.create_account(
        FinanceAccount(
            id="acc-cash",
            owner_jid=owner_jid,
            name="Kas",
            account_type=AccountType.CASH,
            currency="IDR",
            balance=Decimal("2000000"),
            is_active=True,
            created_at=datetime.now(UTC),
        )
    )

    # Budget 500.000
    await repo.upsert_budget(
        FinanceBudget(
            id="b-ent",
            owner_jid=owner_jid,
            category_id=cat.id,
            amount=Decimal("500000"),
            month=8,
            year=2026,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    # Expense 600.000 -> 120%
    tx = FinanceTransaction(
        id="tx-ent",
        owner_jid=owner_jid,
        account_id=acc.id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("600000"),
        category_id=cat.id,
        description="Top up game",
        transaction_date=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
        transfer_to_account_id=None,
        created_at=datetime.now(UTC),
    )
    await repo.add_transaction(tx)

    progress = await repo.get_budget_progress(owner_jid, cat.id, 8, 2026)
    assert progress is not None
    assert progress.spent == Decimal("600000")
    assert progress.remaining == Decimal("-100000")
    assert progress.percentage == 120.0
    assert progress.status == "melebihi budget"


@pytest.mark.asyncio
async def test_multiple_users_isolation(
    async_session_factory, owner_jid: str, other_owner_jid: str
):
    repo = SQLAlchemyFinanceRepository(async_session_factory)

    # User 1 category & budget
    cat1 = await repo.create_category(
        FinanceCategory(
            id="cat-user1",
            owner_jid=owner_jid,
            name="Makanan",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🍜",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )
    await repo.upsert_budget(
        FinanceBudget(
            id="b-user1",
            owner_jid=owner_jid,
            category_id=cat1.id,
            amount=Decimal("1000000"),
            month=8,
            year=2026,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    # User 2 category & budget
    cat2 = await repo.create_category(
        FinanceCategory(
            id="cat-user2",
            owner_jid=other_owner_jid,
            name="Makanan",
            category_type=TransactionType.EXPENSE,  # type: ignore[arg-type]
            icon="🍜",
            is_default=True,
            created_at=datetime.now(UTC),
        )
    )
    await repo.upsert_budget(
        FinanceBudget(
            id="b-user2",
            owner_jid=other_owner_jid,
            category_id=cat2.id,
            amount=Decimal("500000"),
            month=8,
            year=2026,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    # User 1 should only see user 1's budget
    user1_budgets = await repo.get_budgets(owner_jid, 8, 2026)
    assert len(user1_budgets) == 1
    assert user1_budgets[0].amount == Decimal("1000000")

    # User 2 should only see user 2's budget
    user2_budgets = await repo.get_budgets(other_owner_jid, 8, 2026)
    assert len(user2_budgets) == 1
    assert user2_budgets[0].amount == Decimal("500000")

    # User 1 cannot delete User 2's budget
    deleted = await repo.delete_budget(owner_jid, cat2.id, 8, 2026)
    assert deleted is False
    assert (await repo.get_budget(other_owner_jid, cat2.id, 8, 2026)) is not None


# ── FinanceService Validation & Logic Tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_service_invalid_amount_raises_error(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    svc = FinanceService(repo)

    with pytest.raises(InvalidAmountError):
        await svc.set_budget(owner_jid, "makanan", Decimal("0"))

    with pytest.raises(InvalidAmountError):
        await svc.set_budget(owner_jid, "makanan", Decimal("-50000"))


@pytest.mark.asyncio
async def test_service_invalid_category_raises_error(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    svc = FinanceService(repo)

    with pytest.raises(CategoryNotFoundError):
        await svc.set_budget(owner_jid, "KategoriYangSangatTidakAda123XYZ", Decimal("500000"))


@pytest.mark.asyncio
async def test_service_set_get_list_delete_budget(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    svc = FinanceService(repo)

    # Set budget for Makanan & Minuman
    p1 = await svc.set_budget(owner_jid, "makan", Decimal("1000000"), month=8, year=2026)
    assert p1.budget.amount == Decimal("1000000")
    assert p1.budget.category_name == "Makanan & Minuman"
    assert p1.remaining == Decimal("1000000")
    assert p1.percentage == 0.0

    # Set budget for Transport
    p2 = await svc.set_budget(owner_jid, "bensin", Decimal("500000"), month=8, year=2026)
    assert p2.budget.amount == Decimal("500000")
    assert p2.budget.category_name == "Transport"

    # List budgets
    budgets = await svc.list_budgets(owner_jid, month=8, year=2026)
    assert len(budgets) == 2

    # Get single budget
    p_get = await svc.get_budget_progress(owner_jid, "makan", month=8, year=2026)
    assert p_get is not None
    assert p_get.budget.amount == Decimal("1000000")

    # Delete budget
    deleted = await svc.delete_budget(owner_jid, "makan", month=8, year=2026)
    assert deleted is True

    budgets_after = await svc.list_budgets(owner_jid, month=8, year=2026)
    assert len(budgets_after) == 1
    assert budgets_after[0].budget.category_name == "Transport"


# ── Formatters Tests ──────────────────────────────────────────────────────────


def test_format_budget_progress_and_list():
    budget = FinanceBudget(
        id="b-1",
        owner_jid="user@s.whatsapp.net",
        category_id="cat-1",
        amount=Decimal("1000000"),
        month=8,
        year=2026,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        category_name="Makanan & Minuman",
        category_icon="🍜",
    )
    progress = BudgetProgress(
        budget=budget,
        spent=Decimal("650000"),
        remaining=Decimal("350000"),
        percentage=65.0,
        status="aman",
    )

    formatted = format_budget_progress(progress)
    assert "Budget Makanan & Minuman (Agustus 2026)" in formatted
    assert "Rp 1.000.000" in formatted
    assert "Rp 650.000" in formatted
    assert "Rp 350.000" in formatted
    assert "*65%* (Aman)" in formatted

    list_formatted = format_budget_list([progress], 8, 2026)
    assert "Budget Agustus 2026" in list_formatted
    assert "🍜 *Makanan & Minuman*" in list_formatted
    assert "Rp 650.000 / Rp 1.000.000 — *65%* (aman)" in list_formatted


# ── Tool Executor Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_executor_budget_operations(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    svc = FinanceService(repo)
    executor = FinanceToolExecutor(svc)
    user_jid = JID.parse(owner_jid)


    # 1. Create budget
    res_create = await executor.execute(
        "finance_create_budget",
        {"category_name": "makan", "amount": 1000000, "month": 8, "year": 2026},
        user_jid=user_jid,
        chat_jid=user_jid,
    )
    assert '"status": "success"' in res_create
    assert '"amount": 1000000.0' in res_create

    # 2. Get budget
    res_get = await executor.execute(
        "finance_get_budget",
        {"category_name": "makan", "month": 8, "year": 2026},
        user_jid=user_jid,
        chat_jid=user_jid,
    )
    assert '"status": "success"' in res_get
    assert '"percentage": 0.0' in res_get

    # 3. List budgets
    res_list = await executor.execute(
        "finance_list_budgets",
        {"month": 8, "year": 2026},
        user_jid=user_jid,
        chat_jid=user_jid,
    )
    assert '"status": "success"' in res_list
    assert '"count": 1' in res_list

    # 4. Delete budget
    res_del = await executor.execute(
        "finance_delete_budget",
        {"category_name": "makan", "month": 8, "year": 2026},
        user_jid=user_jid,
        chat_jid=user_jid,
    )
    assert '"status": "success"' in res_del


# ── Command Handler Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_command_handler_budget_flow(async_session_factory, owner_jid: str):
    repo = SQLAlchemyFinanceRepository(async_session_factory)
    svc = FinanceService(repo)
    handler = FinanceCommandHandler(svc)

    # Helper to create mock CommandContext
    def create_context(args: list[str]) -> CommandContext:
        ctx = MagicMock(spec=CommandContext)
        ctx.message = MagicMock()
        ctx.message.sender_jid = owner_jid
        ctx.command = MagicMock()
        ctx.command.name = "finance"
        ctx.command.args = args
        ctx.reply = AsyncMock()
        return ctx

    # !finance budget makan 1000000
    ctx1 = create_context(["budget", "makan", "1000000"])
    await handler.handle(ctx1)
    ctx1.reply.assert_called_once()
    reply_text1 = ctx1.reply.call_args[0][0]
    assert "Budget Berhasil Diatur" in reply_text1
    assert "Rp 1.000.000" in reply_text1

    # !finance budget makan
    ctx2 = create_context(["budget", "makan"])
    await handler.handle(ctx2)
    ctx2.reply.assert_called_once()
    reply_text2 = ctx2.reply.call_args[0][0]
    assert "Budget Makanan & Minuman" in reply_text2

    # !finance budget list
    ctx3 = create_context(["budget", "list"])
    await handler.handle(ctx3)
    ctx3.reply.assert_called_once()
    reply_text3 = ctx3.reply.call_args[0][0]
    assert "Makanan & Minuman" in reply_text3

    # !finance budget hapus makan
    ctx4 = create_context(["budget", "hapus", "makan"])
    await handler.handle(ctx4)
    ctx4.reply.assert_called_once()
    reply_text4 = ctx4.reply.call_args[0][0]
    assert "berhasil dihapus" in reply_text4
