"""Skrip scripts/reconcile_finance.py harus konsisten dengan perilaku service yang sebenarnya."""

import importlib.util
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from whatsapp_platform.domain.entities.finance import AccountType
from whatsapp_platform.features.finance.service import FinanceService
from whatsapp_platform.infrastructure.database.base import Base, create_engine_and_session_factory
from whatsapp_platform.infrastructure.database.repositories.finance_repo import SQLAlchemyFinanceRepository

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_finance.py"
OWNER = "628111@s.whatsapp.net"


def _load():
    spec = importlib.util.spec_from_file_location("reconcile_finance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconcile_finance"] = module  # dibutuhkan @dataclass
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def populated(tmp_path: Path):
    db = tmp_path / "app.db"
    engine, factory = create_engine_and_session_factory(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    svc = FinanceService(SQLAlchemyFinanceRepository(factory))
    bca = await svc.create_account(OWNER, "BCA", AccountType.BANK, Decimal("100000"))
    cash = await svc.create_account(OWNER, "Kas", AccountType.CASH, Decimal("0"))
    await svc.add_income(OWNER, Decimal("50000"), "gaji", account_id=bca.id)
    exp = await svc.add_expense(OWNER, Decimal("20000"), "makan", account_id=bca.id)
    await svc.transfer(OWNER, Decimal("10000"), bca.id, cash.id)
    gone = await svc.add_expense(OWNER, Decimal("5000"), "salah", account_id=bca.id)
    await svc.delete_transaction(OWNER, gone.id)
    await svc.reverse_transaction(OWNER, exp.id)
    yield db
    await engine.dispose()


async def test_consistent_database_has_no_problems(populated: Path) -> None:
    module = _load()
    conn = sqlite3.connect(populated)
    report = module.reconcile(conn)
    conn.close()
    assert not report.has_problems, [f.message for f in report.findings]


async def test_tampered_balance_is_detected(populated: Path) -> None:
    module = _load()
    conn = sqlite3.connect(populated)
    conn.execute("UPDATE finance_accounts SET balance = 1 WHERE name = 'BCA'")
    conn.commit()
    report = module.reconcile(conn)
    conn.close()
    assert report.has_problems
    assert any("tidak konsisten" in f.message for f in report.findings)


async def test_script_is_read_only_and_returns_exit_codes(populated: Path, capsys: pytest.CaptureFixture) -> None:
    module = _load()
    before = populated.read_bytes()
    assert module.main([str(populated)]) == 0
    assert "OK" in capsys.readouterr().out
    assert populated.read_bytes() == before
    assert module.main([str(populated.parent / "nope.db")]) == 2
