"""WhatsAppSession aggregate root entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from whatsapp_platform.domain.value_objects.session_status import SessionStatus


@dataclass
class WhatsAppSession:
    id: str
    phone_number: str | None = None
    status: SessionStatus = SessionStatus.INITIALIZING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_connected_at: datetime | None = None
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5

    def set_awaiting_qr(self) -> None:
        self.status = SessionStatus.AWAITING_QR

    def set_awaiting_pairing_code(self) -> None:
        self.status = SessionStatus.AWAITING_PAIRING_CODE

    def connect(self) -> None:
        self.status = SessionStatus.CONNECTED
        self.last_connected_at = datetime.now(UTC)
        self.reconnect_attempts = 0

    def disconnect(self) -> None:
        self.status = SessionStatus.DISCONNECTED

    def start_reconnect(self) -> None:
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.fail(
                f"Exceeded maximum reconnect attempts ({self.max_reconnect_attempts})"
            )
            return
        self.reconnect_attempts += 1
        self.status = SessionStatus.RECONNECTING

    def fail(self, reason: str = "") -> None:
        self.status = SessionStatus.FAILED

    def logout(self) -> None:
        self.status = SessionStatus.LOGGED_OUT

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.CONNECTED
