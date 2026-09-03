"""Contact entity."""

from dataclasses import dataclass

from whatsapp_platform.domain.value_objects.jid import JID


@dataclass
class Contact:
    jid: JID
    name: str | None = None
    push_name: str | None = None
    is_business: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.push_name or str(self.jid)
