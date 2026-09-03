"""Structured Logging setup using structlog.

Configures structlog with:
- ISO 8601 timestamps
- Structured JSON output in production
- Colorized console output in development
- contextvars-based correlation_id support per message
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", app_env: str = "development") -> None:
    """Configure structlog and stdlib logging.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        app_env:   'production' produces JSON, all others produce colored console output.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list = [
        # Merge any bound context vars (e.g. correlation_id, session_id)
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if app_env == "production":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
