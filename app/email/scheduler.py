import asyncio
from datetime import datetime
from typing import Callable, Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings
from app.email.client import EmailMessage, email_client


class EmailPollingScheduler:
    """
    Polling scheduler dengan state persistence di Redis.

    Features:
    - Last-check timestamp disimpan di Redis → tahan restart
    - Configurable interval (default 5 menit)
    - Graceful shutdown via asyncio.Event
    - Pluggable notifier callback (decoupled dari WhatsApp client)
    """

    REDIS_KEY = "email:last_check"
    DEFAULT_INTERVAL = 300  # 5 menit dalam detik

    def __init__(
        self,
        notify_callback: Optional[Callable] = None,
        poll_interval_seconds: int = DEFAULT_INTERVAL,
    ) -> None:
        """
        Args:
            notify_callback    : Async function(emails: list[EmailMessage]) → None
                                 Dipanggil saat ada email baru.
            poll_interval_seconds: Interval polling dalam detik.
        """
        self._notify = notify_callback
        self._interval = poll_interval_seconds
        self._stop_event = asyncio.Event()
        self._redis: Optional[aioredis.Redis] = None
        self._task: Optional[asyncio.Task] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def _get_last_check(self) -> datetime:
        """Ambil timestamp last check dari Redis."""
        try:
            r = await self._get_redis()
            ts = await r.get(self.REDIS_KEY)
            if ts:
                return datetime.fromtimestamp(float(ts))
        except Exception as e:
            logger.warning(f"[EmailScheduler] Redis get failed: {e}")

        # Default: 1 jam lalu (hindari flood notifikasi saat pertama start)
        return datetime.now().replace(minute=0, second=0, microsecond=0)

    async def _set_last_check(self, dt: datetime) -> None:
        """Simpan timestamp last check ke Redis."""
        try:
            r = await self._get_redis()
            await r.set(
                self.REDIS_KEY,
                str(dt.timestamp()),
                ex=86400 * 7,  # TTL 7 hari
            )
        except Exception as e:
            logger.warning(f"[EmailScheduler] Redis set failed: {e}")

    async def start(self) -> None:
        """Start polling loop sebagai background task."""
        if email_client is None:
            logger.warning("[EmailScheduler] Email client not configured, skipping")
            return

        logger.info(
            f"[EmailScheduler] Starting poll every {self._interval}s "
            f"→ {settings.imap_host}"
        )
        self._task = asyncio.create_task(self._poll_loop(), name="email-poller")

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()
        logger.info("[EmailScheduler] Stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                await self._check_new_emails()
            except Exception as e:
                # Jangan crash loop karena satu error
                logger.error(f"[EmailScheduler] Poll error: {e}")

            # Tunggu interval atau sampai stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval,
                )
                break  # stop_event triggered
            except asyncio.TimeoutError:
                pass  # Normal — interval habis, lanjut poll berikutnya

    async def _check_new_emails(self) -> None:
        """Satu siklus polling: fetch → filter baru → notify."""
        last_check = await self._get_last_check()
        now = datetime.now()

        logger.debug(f"[EmailScheduler] Checking since {last_check.strftime('%H:%M:%S')}")

        new_emails = await email_client.fetch_emails(
            since=last_check,
            unread_only=True,
            max_count=10,
        )

        # Filter: hanya email yang benar-benar lebih baru dari last_check
        truly_new = [
            e for e in new_emails
            if e.received_at > last_check
        ]

        if truly_new:
            logger.info(
                f"[EmailScheduler] 🔔 {len(truly_new)} new email(s) detected"
            )
            if self._notify:
                try:
                    await self._notify(truly_new)
                except Exception as e:
                    logger.error(f"[EmailScheduler] Notify callback failed: {e}")
        else:
            logger.debug("[EmailScheduler] No new emails")

        await self._set_last_check(now)

    def set_notify_callback(self, callback: Callable) -> None:
        """Set atau update notify callback setelah inisialisasi."""
        self._notify = callback


# Singleton — di-configure dan di-start dari bot.py
email_scheduler = EmailPollingScheduler(
    poll_interval_seconds=getattr(settings, "email_poll_interval_seconds", 300)
)