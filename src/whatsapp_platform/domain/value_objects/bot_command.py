"""BotCommand Value Object for parsing command prefix and arguments."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BotCommand:
    name: str
    args: list[str] = field(default_factory=list)
    raw_text: str = ""
    prefix: str = "!"

    @classmethod
    def parse(cls, raw_text: str, prefix: str = "!") -> "BotCommand | None":
        """Parse text starting with prefix into a BotCommand instance."""
        if not raw_text or not raw_text.startswith(prefix):
            return None

        parts = raw_text[len(prefix) :].strip().split()
        if not parts or not parts[0]:
            return None

        name = parts[0].lower()
        args = parts[1:]
        return cls(name=name, args=args, raw_text=raw_text, prefix=prefix)
