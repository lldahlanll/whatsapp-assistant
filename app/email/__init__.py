# app/email/__init__.py
from app.email.agent import EmailAgent, email_agent
from app.email.bot_handler import EmailCommandHandler, email_command_handler
from app.email.client import (
    EmailAuthError,
    EmailConnectionError,
    EmailMessage,
    ZimbraEmailClient,
    validate_email_server_config,
)

__all__ = [
    # Agent
    "email_agent",
    "EmailAgent",
    # Command handler
    "email_command_handler",
    "EmailCommandHandler",
    # Client
    "ZimbraEmailClient",
    "EmailMessage",
    # Exceptions
    "EmailAuthError",
    "EmailConnectionError",
    # Validators
    "validate_email_server_config",
]