"""Structured Logging setup using structlog.

Configures structlog with:
- ISO 8601 timestamps
- Structured JSON output in production
- Colorized console output in development
- contextvars-based correlation_id support per message
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

_FILE_HANDLER_NAME = "whatsapp_platform_file"


def setup_logging(
    log_level: str = "INFO",
    app_env: str = "development",
    log_file_path: str | None = None,
    log_file_max_bytes: int = 10 * 1024 * 1024,
    log_file_backup_count: int = 10,
) -> None:
    """Configure structlog and stdlib logging.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        app_env:   'production' produces JSON, all others produce colored console output.
        log_file_path: Jika diisi dan production, log juga ditulis ke file JSON berotasi.
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
    if app_env == "production" and log_file_path:
        _add_rotating_file_handler(Path(log_file_path), level, log_file_max_bytes, log_file_backup_count)

    # httpx/httpcore mencatat setiap request (URL lengkap) di INFO; cukup tampilkan warning ke atas.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _add_rotating_file_handler(path: Path, level: int, max_bytes: int, backup_count: int) -> None:
    """Salinan log ke file (satu baris JSON per event). Gagal membuka file tidak boleh menghentikan app."""
    root = logging.getLogger()
    if any(getattr(h, "name", None) == _FILE_HANDLER_NAME for h in root.handlers):
        return  # setup_logging dipanggil ulang (mis. di test) -> jangan dobel handler
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8", delay=True
        )
    except OSError as exc:
        print(f"File logging disabled: cannot open {path}: {exc}", file=sys.stderr)
        return
    handler.name = _FILE_HANDLER_NAME
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)
