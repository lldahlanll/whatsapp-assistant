"""Session domain events."""

from dataclasses import dataclass

from whatsapp_platform.domain.events.base import DomainEvent
from whatsapp_platform.domain.value_objects.session_status import SessionStatus


@dataclass
class QRCodeGenerated(DomainEvent):
    session_id: str = ""
    qr_code: str = ""  # Base64 or raw QR string


@dataclass
class PairingCodeGenerated(DomainEvent):
    session_id: str = ""
    phone_number: str = ""
    pairing_code: str = ""


@dataclass
class SessionConnected(DomainEvent):
    session_id: str = ""
    phone_number: str | None = None


@dataclass
class SessionDisconnected(DomainEvent):
    session_id: str = ""
    reason: str = ""


@dataclass
class SessionFailed(DomainEvent):
    session_id: str = ""
    reason: str = ""


@dataclass
class SessionStatusChanged(DomainEvent):
    session_id: str = ""
    old_status: SessionStatus | None = None
    new_status: SessionStatus | None = None
