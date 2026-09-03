"""Unit tests for Provider adapters tool calling (Gemini & Groq)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from whatsapp_platform.infrastructure.ai.interfaces import ProviderMessage
from whatsapp_platform.infrastructure.ai.providers.gemini import GeminiProvider
from whatsapp_platform.infrastructure.ai.providers.groq import GroqProvider
from whatsapp_platform.infrastructure.mikrotik.tool_schema import MIKROTIK_TOOLS


@pytest.mark.asyncio
async def test_gemini_provider_tool_calling_request_and_response() -> None:
    """Verify GeminiProvider builds function_declarations payload and parses functionCall response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Mock response containing a functionCall part
    gemini_resp_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "mikrotik_get_traffic",
                                "args": {"interface_name": "ether1"},
                            }
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 50,
            "candidatesTokenCount": 20,
            "totalTokenCount": 70,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = gemini_resp_data
    mock_client.post.return_value = mock_resp

    provider = GeminiProvider(client=mock_client)
    assert provider.supports_tool_calling is True

    messages = [
        ProviderMessage(role="system", content="You are a helpful network assistant."),
        ProviderMessage(role="user", content="Tolong cek traffic ether1"),
    ]

    res = await provider.generate_with_tools(
        messages=messages,
        tools=MIKROTIK_TOOLS,
        api_key="test_gemini_key",
        model="gemini-2.5-flash",
    )

    assert res.tool_calls is not None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "mikrotik_get_traffic"
    assert res.tool_calls[0].arguments == {"interface_name": "ether1"}

    # Verify request payload sent to Gemini API
    call_kwargs = mock_client.post.call_args.kwargs
    json_payload = call_kwargs["json"]
    assert "tools" in json_payload
    assert "function_declarations" in json_payload["tools"][0]
    func_names = [f["name"] for f in json_payload["tools"][0]["function_declarations"]]
    assert "mikrotik_get_traffic" in func_names


@pytest.mark.asyncio
async def test_groq_provider_tool_calling_request_and_response() -> None:
    """Verify GroqProvider builds OpenAI-compatible tools payload and parses tool_calls."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    groq_resp_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "mikrotik_get_health",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {
            "prompt_tokens": 40,
            "completion_tokens": 15,
            "total_tokens": 55,
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = groq_resp_data
    mock_client.post.return_value = mock_resp

    provider = GroqProvider(client=mock_client)
    assert provider.supports_tool_calling is True

    messages = [
        ProviderMessage(role="system", content="You are a helpful network assistant."),
        ProviderMessage(role="user", content="Cek kondisi router dong"),
    ]

    res = await provider.generate_with_tools(
        messages=messages,
        tools=MIKROTIK_TOOLS,
        api_key="test_groq_key",
        model="llama-3.3-70b-versatile",
    )

    assert res.tool_calls is not None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].id == "call_abc123"
    assert res.tool_calls[0].name == "mikrotik_get_health"

    # Verify request payload sent to Groq
    call_kwargs = mock_client.post.call_args.kwargs
    json_payload = call_kwargs["json"]
    assert "tools" in json_payload
    assert json_payload["tool_choice"] == "auto"
