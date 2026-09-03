"""SessionStatusDTO."""

from dataclasses import dataclass


@dataclass
class SessionStatusDTO:
    session_id: str
    status: str
    phone_number: str | None = None
    is_connected: bool = False
    reconnect_attempts: int = 0
