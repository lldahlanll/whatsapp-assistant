"""Common shared schemas for REST API responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    """Generic success response envelope."""

    success: bool = True
    message: str = "OK"
    data: Any | None = None


class ErrorResponse(BaseModel):
    """Generic error response envelope."""

    success: bool = False
    error: str
    detail: str | None = None


class PaginatedResponse(BaseModel):
    """Paginated list response envelope."""

    success: bool = True
    total: int
    page: int
    page_size: int
    data: list[Any]


class TimestampMixin(BaseModel):
    """Mixin for resources with timestamps."""

    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")
