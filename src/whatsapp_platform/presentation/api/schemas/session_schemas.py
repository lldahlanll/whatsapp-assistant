"""Pydantic schemas for session-related endpoints."""

from pydantic import BaseModel, Field


class SessionStatusResponse(BaseModel):
    """Response schema for session status."""

    session_name: str = Field(description="WhatsApp session identifier")
    status: str = Field(description="Current session connection status")
    is_connected: bool = Field(description="True if session is connected to WhatsApp")
    jid: str | None = Field(default=None, description="Logged-in WhatsApp JID (phone@s.whatsapp.net)")
    phone_number: str | None = Field(default=None, description="Logged-in phone number")


class QRCodeResponse(BaseModel):
    """Response schema for QR code retrieval."""

    session_name: str
    qr_data: str | None = Field(default=None, description="QR code data string for scanning")
    qr_available: bool = Field(description="Whether a QR code is currently available")
    message: str = Field(default="", description="Human-readable status message")
