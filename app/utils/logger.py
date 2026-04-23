import sys
from loguru import logger
from pathlib import Path
import os

def setup_logger():
    """Setup logger dengan output ke console dan file."""
    
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Hapus default handler
    logger.remove()

    # Console handler — lebih mudah dibaca saat development
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler — untuk production & debugging
    logger.add(
        log_dir / "bot.log",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
        rotation="10 MB",    # Buat file baru tiap 10MB
        retention="7 days",  # Simpan log 7 hari terakhir
        compression="zip",   # Compress file lama
    )

    return logger