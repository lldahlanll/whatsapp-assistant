"""FastAPI application factory for the WhatsApp Platform REST API.

Creates and configures the FastAPI app with:
- All routers registered
- CORS middleware
- Global exception handlers
- OpenAPI metadata
"""

import time
from typing import cast

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.presentation.api.routers import (
    groups_router,
    health_router,
    messages_router,
    session_router,
)

logger = structlog.get_logger()


def create_api_app(container: object) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        container: The initialized DI Container to attach to app.state.

    Returns:
        Configured FastAPI app instance.
    """
    try:
        settings: Settings = container.resolve(Settings)  # type: ignore[attr-defined]
    except Exception:
        settings = Settings()
    docs_enabled = settings.api_docs_enabled

    app = FastAPI(
        title="WhatsApp Platform API",
        description=(
            "Production-grade REST API for controlling a WhatsApp bot. "
            "Send messages, manage groups, query session status, and more."
        ),
        version="1.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Attach the DI container to app state — accessible via request.app.state.container
    app.state.container = container

    # --- Middleware ---
    cors_origins = cast(list[str], settings.api_cors_origins)
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,  # auth lewat header X-API-Key, bukan cookie
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"],
        )

    # --- Request timing middleware ---
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):  # type: ignore[no-untyped-def]
        start_time = time.monotonic()
        response = await call_next(request)
        process_time = time.monotonic() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response

    # --- Global exception handler ---
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception in API",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"},
        )

    # --- Register routers ---
    app.include_router(health_router)
    app.include_router(session_router)
    app.include_router(messages_router)
    app.include_router(groups_router)

    logger.info("FastAPI app created with all routers registered")
    return app
