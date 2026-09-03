"""Session management router.

Endpoints:
- GET  /api/v1/session         — Current session status
- POST /api/v1/session/disconnect — Disconnect WhatsApp session
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from whatsapp_platform.application.use_cases.manage_session import ManageSessionUseCase
from whatsapp_platform.container import Container
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.presentation.api.dependencies import (
    get_container,
    get_manage_session_uc,
    get_settings,
    verify_api_key,
)
from whatsapp_platform.presentation.api.schemas.common_schemas import SuccessResponse
from whatsapp_platform.presentation.api.schemas.session_schemas import SessionStatusResponse

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/session",
    tags=["Session"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "",
    response_model=SessionStatusResponse,
    summary="Get session status",
    description="Returns the current WhatsApp session connection status.",
)
async def get_session_status(
    settings: Annotated[Settings, Depends(get_settings)],
    container: Annotated[Container, Depends(get_container)],
) -> SessionStatusResponse:
    try:
        session_repo: ISessionRepository = container.resolve(ISessionRepository)  # type: ignore[type-abstract]
        session = await session_repo.get_by_id(settings.session_name)

        if session is None:
            return SessionStatusResponse(
                session_name=settings.session_name,
                status="INITIALIZING",
                is_connected=False,
                jid=None,
                phone_number=None,
            )

        return SessionStatusResponse(
            session_name=session.id,
            status=session.status.value,
            is_connected=session.is_active,
            jid=None,  # Gateway does not expose JID directly; extend if needed
            phone_number=session.phone_number,
        )
    except Exception as exc:
        logger.error("Failed to get session status", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session status",
        ) from exc


@router.post(
    "/disconnect",
    response_model=SuccessResponse,
    summary="Disconnect session",
    description="Gracefully disconnect the active WhatsApp session.",
)
async def disconnect_session(
    settings: Annotated[Settings, Depends(get_settings)],
    manage_session_uc: Annotated[ManageSessionUseCase, Depends(get_manage_session_uc)],
) -> SuccessResponse:
    try:
        await manage_session_uc.disconnect_session(settings.session_name)
        logger.info("Session disconnected via API", session_name=settings.session_name)
        return SuccessResponse(message="Session disconnected successfully")
    except Exception as exc:
        logger.error("Failed to disconnect session", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect session",
        ) from exc
