"""Unit tests for AI SQLite persistence and context cache trimming (Prioritas 1 & Prioritas 4)."""

import os
import tempfile

import pytest

from whatsapp_platform.features.ai.config_store import AIChatConfigStore
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.interfaces import ProviderMessage
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy
from whatsapp_platform.infrastructure.ai.sqlite_store import AISQLiteStore


class DummyProvider:
    @property
    def provider_name(self):
        return "gemini"

    async def generate(self, messages, api_key, model):
        pass


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_config_store_persistence_across_restart(temp_db_path):
    """P1: Config changes persist across process restarts."""
    chat_id = "628123456789@s.whatsapp.net"

    # Store Instance 1: Write configuration
    store1 = AISQLiteStore(db_path=temp_db_path)
    await store1.initialize()
    config_store1 = AIChatConfigStore(db_store=store1)
    await config_store1.initialize()

    await config_store1.set_enabled(chat_id, True)
    await config_store1.set_model(chat_id, "gemini-1.5-flash")
    await config_store1.mark_notice_sent(chat_id)
    await store1.close()

    # Store Instance 2: Simulate restart by loading from same DB file
    store2 = AISQLiteStore(db_path=temp_db_path)
    await store2.initialize()
    config_store2 = AIChatConfigStore(db_store=store2)
    await config_store2.initialize()

    config = await config_store2.get(chat_id)
    assert config.enabled is True
    assert config.model == "gemini-1.5-flash"
    assert config.notice_sent is True
    await store2.close()


@pytest.mark.asyncio
async def test_context_cache_persistence_across_restart(temp_db_path):
    """P1: Context history persists across process restarts."""
    chat_id = "628123456789@s.whatsapp.net"

    # Service Instance 1: Append messages
    store1 = AISQLiteStore(db_path=temp_db_path)
    await store1.initialize()
    ai_service1 = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
        db_store=store1,
    )
    await ai_service1.initialize()
    await ai_service1.append_to_context(chat_id, "user", "Halo Bot")
    await ai_service1.append_to_context(chat_id, "assistant", "Halo! Ada yang bisa dibantu?")
    await store1.close()

    # Service Instance 2: Simulate restart by loading from same DB
    store2 = AISQLiteStore(db_path=temp_db_path)
    await store2.initialize()
    ai_service2 = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
        db_store=store2,
    )
    await ai_service2.initialize()

    context = await ai_service2.get_context(chat_id)
    assert len(context) == 2
    assert context[0] == ProviderMessage(role="user", content="Halo Bot")
    assert context[1] == ProviderMessage(role="assistant", content="Halo! Ada yang bisa dibantu?")
    await store2.close()


@pytest.mark.asyncio
async def test_context_cache_trimming_preserves_system_prompt(temp_db_path):
    """P4: Context trimming keeps system prompt and N most recent messages."""
    chat_id = "628123456789@s.whatsapp.net"
    store = AISQLiteStore(db_path=temp_db_path)
    await store.initialize()

    # Limit to max 4 messages
    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
        db_store=store,
        max_context_messages=4,
    )
    await ai_service.initialize()

    await ai_service.append_to_context(chat_id, "system", "System Instructions")
    await ai_service.append_to_context(chat_id, "user", "Msg 1")
    await ai_service.append_to_context(chat_id, "assistant", "Resp 1")
    await ai_service.append_to_context(chat_id, "user", "Msg 2")
    await ai_service.append_to_context(chat_id, "assistant", "Resp 2")  # Exceeds max 4!

    context = await ai_service.get_context(chat_id)
    assert len(context) == 4
    assert context[0].role == "system"
    assert context[0].content == "System Instructions"
    assert context[1].content == "Resp 1"
    assert context[2].content == "Msg 2"
    assert context[3].content == "Resp 2"

    # Verify SQLite database also trimmed
    db_context = await store.load_all_context()
    assert len(db_context[chat_id]) == 4
    await store.close()


@pytest.mark.asyncio
async def test_clear_context_removes_memory_and_sqlite(temp_db_path):
    """P4: clear_context (!ai reset) empties memory cache and SQLite rows."""
    chat_id = "628123456789@s.whatsapp.net"
    store = AISQLiteStore(db_path=temp_db_path)
    await store.initialize()

    ai_service = AIService(
        providers={"gemini": (DummyProvider(), KeyPool(["k1"]))},
        strategy=FixedPriorityStrategy(["gemini"]),
        db_store=store,
    )
    await ai_service.initialize()
    await ai_service.append_to_context(chat_id, "user", "Test message")

    assert len(await ai_service.get_context(chat_id)) == 1

    # Call reset
    await ai_service.clear_context(chat_id)

    # In-memory context is empty
    assert len(await ai_service.get_context(chat_id)) == 0

    # SQLite rows are deleted
    db_context = await store.load_all_context()
    assert chat_id not in db_context or len(db_context[chat_id]) == 0
    await store.close()
