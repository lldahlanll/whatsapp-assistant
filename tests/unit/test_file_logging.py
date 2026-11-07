"""Log production ditulis juga ke file JSON berotasi (volume app_logs) agar tidak hilang saat redeploy."""

import json
import logging

import structlog

from whatsapp_platform.infrastructure.logging.setup import _FILE_HANDLER_NAME, setup_logging


def _remove_file_handlers() -> None:
    root = logging.getLogger()
    for h in [h for h in root.handlers if h.name == _FILE_HANDLER_NAME]:
        root.removeHandler(h)
        h.close()


def _flush() -> None:
    for h in logging.getLogger().handlers:
        h.flush()


def test_production_writes_json_lines_and_rotates(tmp_path):
    path = tmp_path / "logs" / "app.log"
    try:
        setup_logging("INFO", "production", str(path), log_file_max_bytes=2000, log_file_backup_count=2)
        setup_logging("INFO", "production", str(path))  # dipanggil ulang -> tidak dobel handler
        assert sum(h.name == _FILE_HANDLER_NAME for h in logging.getLogger().handlers) == 1

        log = structlog.get_logger("test")
        log.info("Reminder sent", task="t1")
        _flush()
        first = json.loads(path.read_text().splitlines()[0])
        assert first["event"] == "Reminder sent" and first["task"] == "t1" and first["level"] == "info"

        for i in range(50):
            log.info("filler", i=i, pad="x" * 50)
        _flush()
        # Rotasi: hanya app.log + 2 cadangan disimpan (disk tidak tumbuh tanpa batas), baris terbaru di app.log.
        assert sorted(p.name for p in path.parent.iterdir()) == ["app.log", "app.log.1", "app.log.2"]
        assert json.loads(path.read_text().splitlines()[-1])["i"] == 49
    finally:
        _remove_file_handlers()
        structlog.reset_defaults()


def test_no_file_outside_production(tmp_path):
    path = tmp_path / "app.log"
    try:
        setup_logging("INFO", "development", str(path))
        structlog.get_logger("test").info("hello")
        assert not path.exists()
    finally:
        _remove_file_handlers()
        structlog.reset_defaults()


def test_unwritable_path_does_not_crash(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("not a dir")
    try:
        setup_logging("INFO", "production", str(blocker / "app.log"))
        assert "File logging disabled" in capsys.readouterr().err
    finally:
        _remove_file_handlers()
        structlog.reset_defaults()
