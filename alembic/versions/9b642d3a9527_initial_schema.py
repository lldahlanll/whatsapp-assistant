"""initial_schema — creates all whatsapp platform tables from scratch.

Revision ID: 9b642d3a9527
Revises:
Create Date: 2026-08-05

This is the baseline migration. It creates all four core tables:
  - whatsapp_sessions
  - whatsapp_messages
  - whatsapp_contacts
  - whatsapp_conversations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b642d3a9527"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables for the WhatsApp platform."""
    # --- whatsapp_sessions ---
    op.create_table(
        "whatsapp_sessions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(), nullable=True),
        sa.Column("reconnect_attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- whatsapp_messages ---
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("chat_jid", sa.String(length=100), nullable=False),
        sa.Column("sender_jid", sa.String(length=100), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("push_name", sa.String(length=100), nullable=True),
        sa.Column("is_from_me", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("whatsapp_messages", schema=None) as batch_op:
        batch_op.create_index("ix_whatsapp_messages_chat_jid", ["chat_jid"], unique=False)
        batch_op.create_index("ix_whatsapp_messages_timestamp", ["timestamp"], unique=False)

    # --- whatsapp_contacts ---
    op.create_table(
        "whatsapp_contacts",
        sa.Column("jid", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("push_name", sa.String(length=100), nullable=True),
        sa.Column("is_business", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("jid"),
    )

    # --- whatsapp_conversations ---
    op.create_table(
        "whatsapp_conversations",
        sa.Column("jid", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("is_group", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("jid"),
    )
    with op.batch_alter_table("whatsapp_conversations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_whatsapp_conversations_last_message_at",
            ["last_message_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drop all platform tables."""
    with op.batch_alter_table("whatsapp_conversations", schema=None) as batch_op:
        batch_op.drop_index("ix_whatsapp_conversations_last_message_at")
    op.drop_table("whatsapp_conversations")

    with op.batch_alter_table("whatsapp_messages", schema=None) as batch_op:
        batch_op.drop_index("ix_whatsapp_messages_timestamp")
        batch_op.drop_index("ix_whatsapp_messages_chat_jid")
    op.drop_table("whatsapp_messages")

    op.drop_table("whatsapp_contacts")
    op.drop_table("whatsapp_sessions")
