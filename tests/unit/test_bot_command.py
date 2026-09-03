"""Unit tests for BotCommand Value Object."""

from whatsapp_platform.domain.value_objects.bot_command import BotCommand


def test_parse_valid_command():
    cmd = BotCommand.parse("!ping")
    assert cmd is not None
    assert cmd.name == "ping"
    assert cmd.args == []

    cmd_args = BotCommand.parse("!echo hello world")
    assert cmd_args is not None
    assert cmd_args.name == "echo"
    assert cmd_args.args == ["hello", "world"]


def test_parse_non_command_returns_none():
    assert BotCommand.parse("hello world") is None
    assert BotCommand.parse("") is None
