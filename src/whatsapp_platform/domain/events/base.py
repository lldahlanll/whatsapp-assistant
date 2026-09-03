"""DomainEvent base class."""

import uuid
from dataclasses import KW_ONLY, dataclass, field
from datetime import UTC, datetime


@dataclass
class DomainEvent:
    _: KW_ONLY
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def event_name(self) -> str:
        return self.__class__.__name__
