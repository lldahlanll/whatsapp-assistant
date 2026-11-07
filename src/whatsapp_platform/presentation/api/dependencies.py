"""FastAPI dependency injection helpers.

Provides FastAPI Depends() functions that resolve use cases and config
from the shared DI Container that was initialized by the Application class.
"""

import secrets
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request, status

from whatsapp_platform.application.use_cases.get_conversation import GetConversationHistoryUseCase
from whatsapp_platform.application.use_cases.manage_group import GroupManagementUseCase
from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.application.use_cases.send_media import SendMediaUseCase
from whatsapp_platform.application.use_cases.send_message import SendMessageUseCase
from whatsapp_platform.container import Container
from whatsapp_platform.infrastructure.config.settings import Settings

logger = structlog.get_logger()


def get_container(request: Request) -> Container:
    """Retrieve the DI Container stored in app state."""
    container: Container = request.app.state.container
    return container


def get_settings(container: Annotated[Container, Depends(get_container)]) -> Settings:
    return container.resolve(Settings)


def get_send_message_uc(
    container: Annotated[Container, Depends(get_container)],
) -> SendMessageUseCase:
    return container.resolve(SendMessageUseCase)


def get_send_media_uc(
    container: Annotated[Container, Depends(get_container)],
) -> SendMediaUseCase:
    return container.resolve(SendMediaUseCase)


def get_conversation_uc(
    container: Annotated[Container, Depends(get_container)],
) -> GetConversationHistoryUseCase:
    return container.resolve(GetConversationHistoryUseCase)


def get_manage_session_uc(
    container: Annotated[Container, Depends(get_container)],
) -> ManageSessionUseCase:
    return container.resolve(ManageSessionUseCase)


def get_manage_group_uc(
    container: Annotated[Container, Depends(get_container)],
) -> GroupManagementUseCase:
    return container.resolve(GroupManagementUseCase)


async def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """API Key authentication dependency.

    All /api/v1/* requests must include the correct X-API-Key header.
    Fail closed: if API_KEY is not configured, the protected endpoints are
    unavailable instead of being open to anyone who can reach the port.
    """
    container: Container = request.app.state.container
    settings: Settings = container.resolve(Settings)

    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="REST API is disabled until API_KEY is configured.",
        )

    if not secrets.compare_digest((x_api_key or "").encode(), settings.api_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide it via X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
