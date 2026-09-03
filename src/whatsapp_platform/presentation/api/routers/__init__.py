"""API routers package."""

from whatsapp_platform.presentation.api.routers.groups import router as groups_router
from whatsapp_platform.presentation.api.routers.health import router as health_router
from whatsapp_platform.presentation.api.routers.messages import router as messages_router
from whatsapp_platform.presentation.api.routers.session import router as session_router

__all__ = ["groups_router", "health_router", "messages_router", "session_router"]
