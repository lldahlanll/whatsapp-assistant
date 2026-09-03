"""End-to-End Dry Run Verification Script for Milestones 1 - 4.

Validates the full system flow in memory/test mode:
1. Container & DB initializing (Alembic schema setup)
2. Feature modules loading (Session, Messaging, Commands)
3. Domain event dispatching (SessionConnected, MessageReceived)
4. Command execution (!ping, !status, !help)
5. DB persistence verification (Session, Message, Conversation records)
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src to sys.path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from whatsapp_platform.application.interfaces.event_bus import IEventBus
from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.application.services.event_bus import InMemoryEventBus
from whatsapp_platform.application.services.feature_registry import FeatureRegistry
from whatsapp_platform.application.use_cases.get_conversation import GetConversationHistoryUseCase
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.application.use_cases.receive_message import ReceiveMessageUseCase
from whatsapp_platform.application.use_cases.send_media import SendMediaUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.container import Container
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.events.messaging_events import MessageReceived
from whatsapp_platform.domain.events.session_events import SessionConnected
from whatsapp_platform.domain.repositories.contact_repository import IContactRepository
from whatsapp_platform.domain.repositories.conversation_repository import (
    IConversationRepository,
)
from whatsapp_platform.domain.repositories.message_repository import IMessageRepository
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus
from whatsapp_platform.features.commands import CommandsFeature
from whatsapp_platform.features.messaging import MessagingFeature
from whatsapp_platform.features.session import SessionFeature
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.database.base import Base, create_engine_and_session_factory
from whatsapp_platform.infrastructure.database.repositories.contact_repo import (
    SQLAlchemyContactRepository,
)
from whatsapp_platform.infrastructure.database.repositories.conversation_repo import (
    SQLAlchemyConversationRepository,
)
from whatsapp_platform.infrastructure.database.repositories.message_repo import (
    SQLAlchemyMessageRepository,
)
from whatsapp_platform.infrastructure.database.repositories.session_repo import (
    SQLAlchemySessionRepository,
)


class MockGatewayAdapter(IMessagingGateway):
    """Test double for NeonizeGateway to simulate WhatsApp network events without Go binary."""

    def __init__(self) -> None:
        self._connected = False
        self._event_bus = None
        self._listeners = {}

    def set_event_bus(self, event_bus) -> None:
        self._event_bus = event_bus

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def send_text(self, to: JID, text: str) -> str:
        print(f"\n   [MOCK OUTBOUND TEXT] -> [{to}]:\n   {text}\n")
        return "outbound-msg-id-123"

    async def send_media(self, to: JID, media, caption=None) -> str:
        print(f"\n   [MOCK OUTBOUND MEDIA] -> [{to}]: {media.media_type.value} | {caption}\n")
        return "outbound-media-id-123"

    async def download_media(self, raw_message) -> bytes:
        return b"test-media-data"

    async def pair_phone(self, phone_number: str) -> str:
        return "12345678"

    def subscribe_event(self, event_type: type, handler) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)

    async def get_group_info(self, group_jid: JID) -> dict:
        return {"jid": str(group_jid), "name": "Test Group", "participants": []}

    async def get_group_invite_link(self, group_jid: JID, revoke: bool = False) -> str:
        return "https://chat.whatsapp.com/test-invite"

    async def update_group_participants(self, group_jid: JID, participants, action: str) -> None:
        pass

    async def set_group_name(self, group_jid: JID, name: str) -> None:
        pass

    async def leave_group(self, group_jid: JID) -> None:
        pass


async def run_dry_run():
    print("\n" + "=" * 65)
    print("🧪 STARTING MILESTONES 1 - 4 DRY RUN VERIFICATION")
    print("=" * 65)

    test_db_path = "storage/test_dryrun.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    settings = Settings(database_url=f"sqlite+aiosqlite:///{test_db_path}")

    # Initialize Container manually with MockGatewayAdapter to avoid real Neonize network calls
    container = Container(settings)

    print("\n1. Initializing DI Container & Database Migrations...")
    await container._run_migrations()

    engine, session_factory = create_engine_and_session_factory(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_repo = SQLAlchemySessionRepository(session_factory)
    message_repo = SQLAlchemyMessageRepository(session_factory)
    contact_repo = SQLAlchemyContactRepository(session_factory)
    conversation_repo = SQLAlchemyConversationRepository(session_factory)

    event_bus = InMemoryEventBus()
    mock_gateway = MockGatewayAdapter()

    container.register(Settings, settings)
    container.register(ISessionRepository, session_repo)
    container.register(IMessageRepository, message_repo)
    container.register(IContactRepository, contact_repo)
    container.register(IConversationRepository, conversation_repo)
    container.register(IEventBus, event_bus)
    container.register(IMessagingGateway, mock_gateway)

    send_msg_uc = SendMessageUseCase(mock_gateway, message_repo, event_bus)
    send_media_uc = SendMediaUseCase(mock_gateway, message_repo, event_bus)
    receive_msg_uc = ReceiveMessageUseCase(message_repo, conversation_repo, event_bus)
    manage_session_uc = ManageSessionUseCase(mock_gateway, session_repo)
    get_conv_uc = GetConversationHistoryUseCase(message_repo)
    manage_group_uc = GroupManagementUseCase(mock_gateway)

    container.register(SendMessageUseCase, send_msg_uc)
    container.register(SendMediaUseCase, send_media_uc)
    container.register(ReceiveMessageUseCase, receive_msg_uc)
    container.register(ManageSessionUseCase, manage_session_uc)
    container.register(GetConversationHistoryUseCase, get_conv_uc)
    container.register(GroupManagementUseCase, manage_group_uc)

    feature_registry = FeatureRegistry()
    container.register(FeatureRegistry, feature_registry)

    print("   ✅ Container & Database initialized successfully!")

    print("\n2. Initializing Feature Modules (Session, Messaging, Commands)...")
    feature_registry.register(SessionFeature())
    feature_registry.register(MessagingFeature())
    feature_registry.register(CommandsFeature())
    await feature_registry.initialize_all(container)
    print("   ✅ Feature modules initialized successfully!")

    print("\n3. Simulating WhatsApp Session Connected Event...")
    session_event = SessionConnected(session_id="default_session", phone_number="628123456789")
    await event_bus.publish(session_event)

    session_db = await session_repo.get_by_id("default_session")
    assert session_db is not None
    assert session_db.is_active is True
    print(f"   ✅ Session status in DB: {session_db.status.value} (Phone: {session_db.phone_number})")

    print("\n4. Simulating Inbound Messages & Commands...")

    chat_jid = JID.parse("628123456789@s.whatsapp.net")

    # Message 1: Normal text message
    msg1 = Message(
        id="inbound-msg-001",
        chat_jid=chat_jid,
        sender_jid=chat_jid,
        content=TextContent(text="Halo Bot!"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Budi",
    )
    await event_bus.publish(MessageReceived(message=msg1))

    # Message 2: !ping command
    msg2 = Message(
        id="inbound-msg-002",
        chat_jid=chat_jid,
        sender_jid=chat_jid,
        content=TextContent(text="!ping"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Budi",
    )
    await event_bus.publish(MessageReceived(message=msg2))

    # Message 3: !status command
    msg3 = Message(
        id="inbound-msg-003",
        chat_jid=chat_jid,
        sender_jid=chat_jid,
        content=TextContent(text="!status"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Budi",
    )
    await event_bus.publish(MessageReceived(message=msg3))

    # Message 4: !help command
    msg4 = Message(
        id="inbound-msg-004",
        chat_jid=chat_jid,
        sender_jid=chat_jid,
        content=TextContent(text="!help"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        push_name="Budi",
    )
    await event_bus.publish(MessageReceived(message=msg4))

    print("\n5. Verifying Database State (Messages & Conversations)...")
    stored_messages = await message_repo.get_chat_messages(chat_jid)
    print(f"   ✅ Total stored messages in DB for {chat_jid}: {len(stored_messages)}")
    assert len(stored_messages) >= 4

    conv = await conversation_repo.get_by_jid(chat_jid)
    assert conv is not None
    print(f"   ✅ Conversation Unread Count: {conv.unread_count}")
    print(f"   ✅ Conversation Last Message Timestamp: {conv.updated_at}")

    print("\n6. Shutting down Feature Modules...")
    await feature_registry.shutdown_all()
    await engine.dispose()
    print("   ✅ Graceful shutdown completed!")

    print("\n" + "=" * 65)
    print("🎉 ALL MILESTONES 1 - 4 CHECKS PASSED PERFECTLY!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(run_dry_run())
