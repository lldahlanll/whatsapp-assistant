"""Tool call dari LLM hanya boleh dieksekusi jika tool itu ditawarkan pada giliran tersebut."""

from unittest.mock import AsyncMock

from whatsapp_platform.domain.value_objects.jid import JID
from whatsapp_platform.infrastructure.ai.ai_service import AIService
from whatsapp_platform.infrastructure.ai.interfaces import AIResponse, ProviderMessage, ToolCall
from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition

USER = JID.parse("628123456789@s.whatsapp.net")


def _response(text: str = "", calls: list[ToolCall] | None = None) -> AIResponse:
    return AIResponse(text=text, provider_used="t", key_index_used=0, token_usage=None, latency_ms=0, tool_calls=calls)


def _service(responses: list[AIResponse]) -> AIService:
    service = AIService.__new__(AIService)
    service._call_provider_with_retry = AsyncMock(side_effect=responses)  # type: ignore[method-assign]
    return service


async def test_unoffered_tool_is_rejected_and_never_executed() -> None:
    service = _service([
        _response(calls=[ToolCall(id="1", name="finance_reset_data", arguments={"confirm": True})]),
        _response(text="selesai"),
    ])
    executor = AsyncMock()

    result = await service.generate_reply_with_tools(
        chat_jid=str(USER),
        messages=[ProviderMessage(role="user", content="catat kopi 10rb")],
        tool_executor=executor,
        tools=[ToolDefinition(name="finance_add_expense", description="x")],
        user_jid=USER,
        wa_chat_jid=USER,
        user_text="catat kopi 10rb",
    )

    executor.execute.assert_not_called()
    assert result.text == "selesai"


async def test_offered_tool_is_executed_with_user_text() -> None:
    service = _service([
        _response(calls=[ToolCall(id="1", name="finance_get_balance", arguments={})]),
        _response(text="ok"),
    ])
    executor = AsyncMock()
    executor.execute.return_value = '{"status": "success"}'

    await service.generate_reply_with_tools(
        chat_jid=str(USER),
        messages=[ProviderMessage(role="user", content="saldo")],
        tool_executor=executor,
        tools=[ToolDefinition(name="finance_get_balance", description="x")],
        user_jid=USER,
        wa_chat_jid=USER,
        message_id="m1",
        user_text="saldo",
    )

    executor.execute.assert_awaited_once()
    assert executor.execute.call_args.kwargs["user_text"] == "saldo"
