"""JID (Jabber Identifier) Value Object for WhatsApp numbers and groups."""

import re
from dataclasses import dataclass

from whatsapp_platform.domain.exceptions.exceptions import InvalidJIDError


@dataclass(frozen=True)
class JID:
    user: str
    server: str

    def __post_init__(self) -> None:
        if not self.user:
            raise InvalidJIDError(str(self), "User part cannot be empty")
        if self.server not in (
            "s.whatsapp.net",
            "g.us",
            "broadcast",
            "newsletter",
            "lid",
        ):
            raise InvalidJIDError(str(self), f"Unsupported server '{self.server}'")

    @classmethod
    def parse(cls, raw: str) -> "JID":
        """Parse raw string into JID object."""
        if not raw or not isinstance(raw, str):
            raise InvalidJIDError(str(raw), "JID string must be a non-empty string")

        cleaned = raw.strip()

        if "@" in cleaned:
            user_part, server_part = cleaned.split("@", 1)
            # Remove device/agent suffix if present e.g. 628123:1 or 628123.0:1
            user_clean = user_part.split(":")[0].split(".")[0]
            if not user_clean:
                raise InvalidJIDError(raw, "User part of JID cannot be empty")
            return cls(user=user_clean, server=server_part)

        # If no @ is present, assume phone number or raw user ID
        digits = re.sub(r"\D", "", cleaned)
        if not digits:
            raise InvalidJIDError(raw, "No digits found in phone number JID")
        return cls(user=digits, server="s.whatsapp.net")

    @classmethod
    def create_user(cls, phone_number: str) -> "JID":
        """Helper to create user JID from phone number."""
        digits = re.sub(r"\D", "", phone_number)
        return cls(user=digits, server="s.whatsapp.net")

    @classmethod
    def create_group(cls, group_id: str) -> "JID":
        """Helper to create group JID."""
        cleaned_id = group_id.split("@")[0]
        return cls(user=cleaned_id, server="g.us")

    @property
    def is_group(self) -> bool:
        return self.server == "g.us"

    @property
    def is_user(self) -> bool:
        return self.server in ("s.whatsapp.net", "lid")

    def __str__(self) -> str:
        return f"{self.user}@{self.server}"
