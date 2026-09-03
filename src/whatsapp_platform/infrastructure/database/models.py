"""SQLAlchemy ORM models."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from whatsapp_platform.infrastructure.database.base import Base


class SessionModel(Base):
    __tablename__ = "whatsapp_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="INITIALIZING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconnect_attempts: Mapped[int] = mapped_column(Integer, default=0)


class MessageModel(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    chat_jid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sender_jid: Mapped[str] = mapped_column(String(100), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False, default="TEXT")
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), index=True
    )
    push_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_from_me: Mapped[bool] = mapped_column(Boolean, default=False)


class ContactModel(Base):
    __tablename__ = "whatsapp_contacts"

    jid: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    push_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_business: Mapped[bool] = mapped_column(Boolean, default=False)


class ConversationModel(Base):
    """Represents a WhatsApp conversation (chat thread)."""

    __tablename__ = "whatsapp_conversations"

    jid: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )


class FinanceAccountModel(Base):
    """Rekening / dompet milik seorang user."""

    __tablename__ = "finance_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_jid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, default="cash")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="IDR")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class FinanceCategoryModel(Base):
    """Kategori pemasukan / pengeluaran."""

    __tablename__ = "finance_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_jid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_type: Mapped[str] = mapped_column(String(20), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class FinanceTransactionModel(Base):
    """Transaksi keuangan (pemasukan, pengeluaran, transfer)."""

    __tablename__ = "finance_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    human_tx_id: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    owner_jid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, default=lambda: datetime.now(UTC)
    )
    transfer_to_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reversal_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class FinanceBudgetModel(Base):
    """Budget pengeluaran per kategori per bulan."""

    __tablename__ = "finance_budgets"
    __table_args__ = (
        UniqueConstraint(
            "owner_jid", "category_id", "month", "year",
            name="uq_finance_budgets_owner_cat_month_year"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_jid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
