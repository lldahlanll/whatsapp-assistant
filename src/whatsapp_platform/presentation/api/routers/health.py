"""Health check router.

Provides liveness and readiness endpoints for monitoring and orchestration.
"""

from fastapi import APIRouter, Request

from whatsapp_platform.presentation.api.schemas.common_schemas import SuccessResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=SuccessResponse,
    summary="Liveness check",
    description="Returns 200 OK if the API server is alive.",
)
async def health_liveness() -> SuccessResponse:
    return SuccessResponse(message="WhatsApp Platform API is running")


@router.get(
    "/health/ready",
    response_model=SuccessResponse,
    summary="Readiness check",
    description="Returns 200 OK if the application and container are initialized.",
)
async def health_readiness(request: Request) -> SuccessResponse:
    container = getattr(request.app.state, "container", None)
    if container is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application container is not initialized",
        )
    return SuccessResponse(message="WhatsApp Platform is ready")
