"""Batas per pengirim di grup + peringatan konfigurasi MikroTik + batas piksel gambar."""

import io

from PIL import Image

from whatsapp_platform.features.ai.rate_guard import PerChatRateGuard
from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.shared.utils import media_processor
from whatsapp_platform.shared.utils.media_processor import MediaProcessor

GROUP = "120363@g.us"


async def test_one_member_cannot_exhaust_group_quota() -> None:
    guard = PerChatRateGuard(max_requests=5, window_seconds=60, per_user_max_requests=2)

    assert await guard.check_and_record(GROUP, sender="alice")
    assert await guard.check_and_record(GROUP, sender="alice")
    assert not await guard.check_and_record(GROUP, sender="alice")  # alice habis jatah
    # Anggota lain tetap dilayani; permintaan alice yang ditolak tidak memakan kuota grup.
    assert await guard.check_and_record(GROUP, sender="bob")
    assert await guard.check_and_record(GROUP, sender="carol")
    assert await guard.check_and_record(GROUP, sender="dave")
    assert not await guard.check_and_record(GROUP, sender="erin")  # kuota grup (5) habis


async def test_without_sender_behaviour_is_unchanged() -> None:
    guard = PerChatRateGuard(max_requests=2, window_seconds=60, per_user_max_requests=1)
    assert await guard.check_and_record("628@s.whatsapp.net")
    assert await guard.check_and_record("628@s.whatsapp.net")
    assert not await guard.check_and_record("628@s.whatsapp.net")


async def test_per_user_limit_disabled_by_default() -> None:
    guard = PerChatRateGuard(max_requests=3, window_seconds=60)
    assert all([await guard.check_and_record(GROUP, sender="alice") for _ in range(3)])


async def test_expired_windows_are_dropped(monkeypatch) -> None:
    from whatsapp_platform.features.ai import rate_guard as mod

    clock = {"t": 100.0}
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock["t"])
    guard = PerChatRateGuard(max_requests=5, window_seconds=60, per_user_max_requests=2)
    await guard.check_and_record(GROUP, sender="alice")

    clock["t"] += 61
    assert await guard.check_and_record(GROUP, sender="alice")
    assert len(guard._windows) == 1 and len(guard._user_windows) == 1


def test_mikrotik_security_warnings() -> None:
    base = {"mikrotik_enabled": True, "mikrotik_host": "192.168.88.1"}
    assert "cleartext" in Settings(**base, mikrotik_use_ssl=False).mikrotik_security_warnings()[0]
    assert "MITM" in Settings(**base, mikrotik_use_ssl=True, mikrotik_verify_ssl=False).mikrotik_security_warnings()[0]
    assert Settings(**base, mikrotik_use_ssl=True, mikrotik_verify_ssl=True).mikrotik_security_warnings() == []
    assert Settings(mikrotik_enabled=False).mikrotik_security_warnings() == []


def test_oversized_image_is_not_decoded(monkeypatch) -> None:
    monkeypatch.setattr(media_processor, "MAX_IMAGE_PIXELS", 100)  # 10x10
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(buf, format="PNG")
    raw = buf.getvalue()

    assert MediaProcessor.compress_image(raw) == raw
