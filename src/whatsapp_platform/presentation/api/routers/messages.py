"""Messages router.

Endpoints:
- POST /api/v1/messages/send         — Send a text message
- GET  /api/v1/messages/{jid}/history — Get conversation history for a JID
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from whatsapp_platform.application.use_cases.get_conversation import GetConversationHistoryUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.domain.entities.message import Message
from whatsapp_platform.domain.exceptions.exceptions import GatewayException, InvalidJIDError
from whatsapp_platform.domain.value_objects.message_content import MediaContent, TextContent
from whatsapp_platform.presentation.api.dependencies import (
    get_conversation_uc,
    get_send_message_uc,
    verify_api_key,
)
from whatsapp_platform.presentation.api.schemas.message_schemas import (
    ConversationHistoryResponse,
    MessageResponse,
    SendMessageRequest,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/messages",
    tags=["Messages"],
    dependencies=[Depends(verify_api_key)],
)


def _message_to_response(msg: Message) -> MessageResponse:
    """Convert a domain Message entity to a MessageResponse schema."""
    text: str | None = None
    media_type: str | None = None

    if isinstance(msg.content, TextContent):
        text = msg.content.text
    elif isinstance(msg.content, MediaContent):
        media_type = msg.content.media_type.value

    return MessageResponse(
        id=msg.id,
        chat_jid=str(msg.chat_jid),
        sender_jid=str(msg.sender_jid),
        direction=msg.direction.value,
        status=msg.status.value,
        text=text,
        media_type=media_type,
        is_from_me=msg.is_from_me,
        push_name=msg.push_name,
        timestamp=msg.timestamp,
    )


@router.post(
    "/send",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send text message",
    description="Send a WhatsApp text message to a contact or group JID.",
)
async def send_message(
    body: SendMessageRequest,
    send_message_uc: Annotated[SendMessageUseCase, Depends(get_send_message_uc)],
) -> MessageResponse:
    try:
        message = await send_message_uc.execute(to_jid_str=body.to, text=body.text)
        logger.info("Message sent via API", to=body.to)
        return _message_to_response(message)
    except GatewayException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp gateway error: {exc}",
        ) from exc
    except (ValueError, InvalidJIDError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid JID format: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed to send message via API", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message",
        ) from exc


@router.get(
    "/{jid}/history",
    response_model=ConversationHistoryResponse,
    summary="Get conversation history",
    description=(
        "Retrieve stored message history for a specific contact or group JID. "
        "JID must be URL-encoded (e.g. `628123456789%40s.whatsapp.net`)."
    ),
)
async def get_conversation_history(
    jid: str,
    get_conv_uc: Annotated[GetConversationHistoryUseCase, Depends(get_conversation_uc)],
    limit: int = Query(default=50, ge=1, le=200, description="Max messages to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> ConversationHistoryResponse:
    try:
        messages = await get_conv_uc.execute(chat_jid_str=jid, limit=limit, offset=offset)
        return ConversationHistoryResponse(
            chat_jid=jid,
            messages=[_message_to_response(m) for m in messages],
            total=len(messages),
            limit=limit,
            offset=offset,
        )
    except (ValueError, InvalidJIDError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid JID format: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed to get conversation history", jid=jid, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation history",
        ) from exc
