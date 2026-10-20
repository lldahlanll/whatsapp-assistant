"""Unit tests for NineRouterProvider and 9router integration."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.constants import (
    DEFAULT_MODELS,
    DEFAULT_PROVIDER_ORDER,
    NINEROUTER_INTENT_MODEL_MAP,
    SUPPORTED_MODELS,
)
from whatsapp_platform.infrastructure.ai.interfaces import (
    AIResponse,
    AllProvidersExhaustedError,
    ProviderError,
    ProviderMessage,
    RateLimitError,
    ToolCall,
)
from whatsapp_platform.infrastructure.ai.key_pool import KeyPool
from whatsapp_platform.infrastructure.ai.provider_strategy import FixedPriorityStrategy
from whatsapp_platform.infrastructure.ai.providers.ninerouter import (
    NineRouterProvider,
    _build_openai_messages,
    _parse_retry_after,
)
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS


@pytest.mark.asyncio
async def test_ninerouter_provider_basic_generation() -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Halo! Ada yang bisa saya bantu?",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 10,
            "total_tokens": 25,
        },
    }
    mock_client.post.return_value = mock_resp

    provider = NineRouterProvider(client=mock_client, base_url="http://localhost:4000/v1")
    assert provider.provider_name == "ninerouter"
    assert provider.supports_tool_calling is True

    messages = [
        ProviderMessage(role="system", content="You are a helpful assistant."),
        ProviderMessage(role="user", content="Halo"),
    ]

    response = await provider.generate(messages=messages, api_key="secret-key", model="chat-pool")

    assert response.text == "Halo! Ada yang bisa saya bantu?"
    assert response.provider_used == "ninerouter"
    assert response.token_usage == {
        "prompt_tokens": 15,
        "completion_tokens": 10,
        "total_tokens": 25,
    }

    call_args = mock_client.post.call_args
    assert call_args.args[0] == "http://localhost:4000/v1/chat/completions"
    headers = call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-key"
    assert headers["X-Title"] == "WhatsApp Platform AI"
    payload = call_args.kwargs["json"]
    assert payload["model"] == "chat-pool"
    assert len(payload["messages"]) == 2


@pytest.mark.asyncio
async def test_ninerouter_provider_tool_calling() -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "mikrotik_get_traffic",
                                "arguments": json.dumps({"interface_name": "ether1"}),
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
        },
    }
    mock_client.post.return_value = mock_resp

    provider = NineRouterProvider(client=mock_client, base_url="http://localhost:4000/v1/")
    messages = [
        ProviderMessage(role="user", content="Cek traffic ether1"),
    ]

    response = await provider.generate_with_tools(
        messages=messages,
        tools=MIKROTIK_TOOLS,
        api_key="secret-key",
        model="tools-pool",
    )

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call_123"
    assert response.tool_calls[0].name == "mikrotik_get_traffic"
    assert response.tool_calls[0].arguments == {"interface_name": "ether1"}

    call_kwargs = mock_client.post.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["model"] == "tools-pool"
    assert "tools" in payload
    assert payload["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_ninerouter_provider_rate_limit_and_error() -> None:
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Test 429
    resp_429 = MagicMock(spec=httpx.Response)
    resp_429.status_code = 429
    resp_429.is_success = False
    resp_429.headers = {"retry-after": "15"}
    mock_client.post.return_value = resp_429

    provider = NineRouterProvider(client=mock_client, base_url="http://localhost:4000/v1")
    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate([ProviderMessage(role="user", content="hi")], "key", "chat-pool")
    assert exc_info.value.retry_after == 15.0

    # Test 500 error
    resp_500 = MagicMock(spec=httpx.Response)
    resp_500.status_code = 500
    resp_500.is_success = False
    resp_500.text = "Internal Server Error"
    resp_500.json.return_value = {"error": {"message": "Server failure"}}
    mock_client.post.return_value = resp_500

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate([ProviderMessage(role="user", content="hi")], "key", "chat-pool")
    assert "Server failure" in str(exc_info.value)


def test_build_openai_messages() -> None:
    msgs = [
        ProviderMessage(role="system", content="System msg"),
        ProviderMessage(role="user", content="User msg"),
        ProviderMessage(
            role="assistant",
            content="Thinking...",
            tool_calls=[ToolCall(id="c1", name="fn1", arguments={"a": 1})],
        ),
        ProviderMessage(role="tool", content='{"status": "ok"}', tool_call_id="c1", name="fn1"),
    ]
    formatted = _build_openai_messages(msgs)
    assert len(formatted) == 4
    assert formatted[0] == {"role": "system", "content": "System msg"}
    assert formatted[1] == {"role": "user", "content": "User msg"}
    assert formatted[2]["role"] == "assistant"
    assert formatted[2]["tool_calls"][0]["id"] == "c1"
    assert formatted[2]["tool_calls"][0]["function"]["name"] == "fn1"
    assert formatted[3] == {
        "role": "tool",
        "tool_call_id": "c1",
        "name": "fn1",
        "content": '{"status": "ok"}',
    }


def test_settings_ninerouter() -> None:
    settings = Settings(
        ninerouter_api_keys="key1, key2",
        ninerouter_base_url="http://router:4000/v1",
        ninerouter_model_chat="my-chat-model",
        ninerouter_model_tools="my-tools-model",
        ninerouter_model_vision="my-vision-model",
    )
    assert settings.ninerouter_api_keys == ["key1", "key2"]
    assert settings.ninerouter_base_url == "http://router:4000/v1"
    assert settings.ninerouter_model_chat == "my-chat-model"
    assert settings.ninerouter_model_tools == "my-tools-model"
    assert settings.ninerouter_model_vision == "my-vision-model"


def test_constants_ninerouter() -> None:
    assert "ninerouter" in SUPPORTED_MODELS
    assert "chat-pool" in SUPPORTED_MODELS["ninerouter"]
    assert "tools-pool" in SUPPORTED_MODELS["ninerouter"]
    assert "vision-pool" in SUPPORTED_MODELS["ninerouter"]
    assert DEFAULT_MODELS["ninerouter"] == "chat-pool"
    assert DEFAULT_PROVIDER_ORDER[0] == "ninerouter"
    assert NINEROUTER_INTENT_MODEL_MAP["chat"] == "chat-pool"
    assert NINEROUTER_INTENT_MODEL_MAP["finance"] == "tools-pool"
    assert NINEROUTER_INTENT_MODEL_MAP["network"] == "tools-pool"


@pytest.mark.asyncio
async def test_ai_service_intent_routing_ninerouter() -> None:
    mock_adapter = AsyncMock(spec=NineRouterProvider)
    mock_adapter.supports_tool_calling = True
    mock_adapter.provider_name = "ninerouter"
    mock_adapter.generate.return_value = AIResponse(
        text="Response",
        provider_used="ninerouter",
        key_index_used=0,
        token_usage=None,
        latency_ms=10.0,
    )

    pool = KeyPool(["key1"], default_cooldown_seconds=60.0)
    strategy = FixedPriorityStrategy(["ninerouter"])
    ai_service = AIService(
        providers={"ninerouter": (mock_adapter, pool)},
        strategy=strategy,
    )

    messages = [ProviderMessage(role="user", content="Halo")]

    # Intent chat -> chat-pool
    await ai_service.generate_reply(
        chat_jid="test@s.whatsapp.net",
        messages=messages,
        intent="chat",
    )
    assert mock_adapter.generate.call_args.args[2] == "chat-pool"

    # Intent finance -> tools-pool
    await ai_service.generate_reply(
        chat_jid="test@s.whatsapp.net",
        messages=messages,
        intent="finance",
    )
    assert mock_adapter.generate.call_args.args[2] == "tools-pool"

    # Intent network -> tools-pool
    await ai_service.generate_reply(
        chat_jid="test@s.whatsapp.net",
        messages=messages,
        intent="network",
    )
    assert mock_adapter.generate.call_args.args[2] == "tools-pool"

    # Model override takes precedence
    await ai_service.generate_reply(
        chat_jid="test@s.whatsapp.net",
        messages=messages,
        model_override="custom-override-model",
        intent="chat",
    )
    assert mock_adapter.generate.call_args.args[2] == "custom-override-model"


@pytest.mark.asyncio
async def test_ai_service_injected_intent_models_do_not_touch_constants() -> None:
    mock_adapter = AsyncMock(spec=NineRouterProvider)
    mock_adapter.supports_tool_calling = True
    mock_adapter.generate.return_value = AIResponse(
        text="ok", provider_used="ninerouter", key_index_used=0, token_usage=None, latency_ms=1.0
    )
    ai_service = AIService(
        providers={"ninerouter": (mock_adapter, KeyPool(["key1"]))},
        strategy=FixedPriorityStrategy(["ninerouter"]),
        intent_models={"ninerouter": {"chat": "my-chat", "finance": "my-tools"}},
    )
    messages = [ProviderMessage(role="user", content="Halo")]

    await ai_service.generate_reply(chat_jid="c", messages=messages, intent="finance")
    assert mock_adapter.generate.call_args.args[2] == "my-tools"
    assert NINEROUTER_INTENT_MODEL_MAP["finance"] == "tools-pool"


@pytest.mark.asyncio
async def test_model_override_only_applies_to_owning_provider() -> None:
    def make_adapter(name: str) -> AsyncMock:
        adapter = AsyncMock(spec=NineRouterProvider)
        adapter.supports_tool_calling = True
        adapter.generate.side_effect = ProviderError(f"{name} down")
        return adapter

    nine = make_adapter("ninerouter")
    gemini = make_adapter("gemini")
    gemini.generate.side_effect = None
    gemini.generate.return_value = AIResponse(
        text="ok", provider_used="gemini", key_index_used=0, token_usage=None, latency_ms=1.0
    )
    ai_service = AIService(
        providers={"ninerouter": (nine, KeyPool(["k"])), "gemini": (gemini, KeyPool(["k"]))},
        strategy=FixedPriorityStrategy(["ninerouter", "gemini"]),
    )
    messages = [ProviderMessage(role="user", content="Halo")]

    # Override milik gemini → gemini dicoba lebih dulu dengan model override.
    await ai_service.generate_reply(chat_jid="c", messages=messages, model_override="gemini-3.5-flash")
    assert gemini.generate.call_args.args[2] == "gemini-3.5-flash"
    nine.generate.assert_not_called()

    # Gemini gagal → ninerouter memakai modelnya sendiri, bukan override gemini.
    gemini.generate.side_effect = ProviderError("gemini down")
    with pytest.raises(AllProvidersExhaustedError):
        await ai_service.generate_reply(chat_jid="c", messages=messages, model_override="gemini-3.5-flash")
    assert nine.generate.call_args.args[2] == "chat-pool"
