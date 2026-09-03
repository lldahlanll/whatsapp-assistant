"""Unit tests for ReceiveMessageUseCase."""

from datetime import UTC, datetime

import pytest

from whatsapp_platform.application.use_cases.receive_message import (
    ReceiveMessageUseCase,
)
from whatsapp_platform.domain.entities.message import Message, MessageDirection
from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.domain.value_objects.message_content import TextContent
from whatsapp_platform.domain.value_objects.message_status import MessageStatus


class MockMessageRepo:
    def __init__(self) -> None:
        self.messages = []

    async def save(self, message: Message) -> None:
        self.messages.append(message)

    async def get_by_id(self, message_id: str):
        for m in self.messages:
            if m.id == message_id:
                return m
        return None

    async def get_chat_messages(self, chat_jid, limit: int = 50, offset: int = 0):
        return [m for m in self.messages if str(m.chat_jid) == str(chat_jid)]


class MockConversationRepo:
    def __init__(self) -> None:
        self.conversations = {}

    async def save(self, conversation) -> None:
        self.conversations[str(conversation.chat_jid)] = conversation

    async def get_by_jid(self, jid):
        return self.conversations.get(str(jid))

    async def list_all(self, limit: int = 50, offset: int = 0):
        return list(self.conversations.values())

    async def delete(self, jid) -> None:
        self.conversations.pop(str(jid), None)


@pytest.mark.asyncio
async def test_receive_message_use_case_persists_message_and_updates_conversation():
    msg_repo = MockMessageRepo()
    conv_repo = MockConversationRepo()

    use_case = ReceiveMessageUseCase(msg_repo, conv_repo)

    msg = Message(
        id="msg-101",
        chat_jid=JID.parse("628123456789@s.whatsapp.net"),
        sender_jid=JID.parse("628123456789@s.whatsapp.net"),
        content=TextContent(text="Hello Assistant!"),
        direction=MessageDirection.INBOUND,
        status=MessageStatus.DELIVERED,
        timestamp=datetime.now(UTC),
        is_from_me=False,
    )

    ret = await use_case.execute(msg)
    assert ret.id == "msg-101"

    # 1. Message saved
    assert len(msg_repo.messages) == 1
    assert msg_repo.messages[0].id == "msg-101"

    # 2. Conversation created & updated
    conv = await conv_repo.get_by_jid(msg.chat_jid)
    assert conv is not None
    assert conv.unread_count == 1
    assert conv.last_message.id == "msg-101"
