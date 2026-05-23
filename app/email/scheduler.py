# app/email/scheduler.py
"""
Multi-user email polling scheduler dengan per-user opt-in.

Arsitektur:
- Satu asyncio polling loop untuk semua opted-in users
- Per-user last_check timestamp di Redis
- Per-user ZimbraEmailClient instance (dari credential store)
- Notify callback di-inject dari bot.py (decoupled)

Redis keys:
  email:notify:{jid}         → opt-in flag (via NotifyOptInManager)
  email:last_check:{jid}     → timestamp per user
"""
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Optional

import redis.asyncio as aioredis
from loguru import logger

from app.auth.credential_store import credential_store
from app.auth.middleware import check_auth
from app.config import settings
from app.email.client import EmailAuthError, EmailConnectionError, ZimbraEmailClient
from app.email.notify_manager import notify_opt_in_manager


class MultiUserEmailScheduler:
    """
    Polling scheduler yang iterate semua opted-in users per interval.

    Callback signature:
        async def notify(jid: str, emails: list[EmailMessage]) -> None
    """

    LAST_CHECK_PREFIX = "email:last_check:"
    LAST_CHECK_TTL = 86400 * 7  # 7 hari
    DEFAULT_INTERVAL = 300  # 5 menit

    def __init__(self, poll_interval_seconds: int = DEFAULT_INTERVAL) -> None:
        self._interval = poll_interval_seconds
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None
        # Injected dari bot.py — async def(jid: str, emails: list) -> None
        self._notify_callback: Optional[Callable] = None

    def set_notify_callback(self, callback: Callable) -> None:
        self._notify_callback = callback

    async def start(self) -> None:
        if not settings.multi_user_configured:
            logger.warning(
                "[Scheduler] multi_user_configured=False — scheduler skipped"
            )
            return
        if self._task and not self._task.done():
            logger.warning("[Scheduler] Already running, skip start")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop(), name="email-scheduler")
        logger.info(
            f"[Scheduler] ✓ Started — poll every {self._interval}s"
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("[Scheduler] Stopped")

    # ── Redis helpers ─────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _last_check_key(self, jid: str) -> str:
        return f"{self.LAST_CHECK_PREFIX}{jid}"

    async def _get_last_check(self, jid: str) -> datetime:
        try:
            r = await self._get_redis()
            ts = await r.get(self._last_check_key(jid))
            if ts:
                return datetime.fromtimestamp(float(ts))
        except Exception as e:
            logger.warning(f"[Scheduler] Redis get last_check failed for {jid}: {e}")
        # Default: sekarang — jangan proses email lama (restart / TTL expired)
        # User bisa /email today untuk catch-up manual
        return datetime.now()

    async def _set_last_check(self, jid: str, dt: datetime) -> None:
        try:
            r = await self._get_redis()
            await r.set(
                self._last_check_key(jid),
                str(dt.timestamp()),
                ex=self.LAST_CHECK_TTL,
            )
        except Exception as e:
            logger.warning(f"[Scheduler] Redis set last_check failed for {jid}: {e}")

    async def reset_last_check(self, jid: str) -> None:
        """Reset last_check ke 'sekarang' — dipakai saat user baru opt-in."""
        await self._set_last_check(jid, datetime.now())

    # ── Polling loop ──────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                opted_in_jids = await notify_opt_in_manager.get_all_opted_in()
                if opted_in_jids:
                    logger.debug(
                        f"[Scheduler] Polling {len(opted_in_jids)} opted-in user(s)"
                    )
                    await asyncio.gather(
                        *[self._check_user(jid) for jid in opted_in_jids],
                        return_exceptions=True,  # Jangan crash semua kalau 1 user error
                    )
                else:
                    logger.debug("[Scheduler] No opted-in users, skipping")
            except Exception as e:
                logger.error(f"[Scheduler] Poll loop error: {e}")

            # Tunggu interval atau stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self._interval),
                )
                break  # stop triggered
            except asyncio.TimeoutError:
                pass  # Normal interval expiry

    async def _check_user(self, jid: str) -> None:
        """
        Satu polling cycle untuk satu user.
        Handles: credential not found, auth error (auto-opt-out), connection error.
        """
        # Ambil credential dari store (bukan dari session — scheduler berjalan background)
        credential = await credential_store.get(jid)
        if credential is None:
            # User tidak punya credential — opt-out otomatis
            logger.warning(
                f"[Scheduler] {jid} has no credential — auto opt-out"
            )
            await notify_opt_in_manager.disable(jid)
            return

        last_check = await self._get_last_check(jid)
        now = datetime.now()

        try:
            client = ZimbraEmailClient.for_user(credential)
            new_emails = await client.fetch_emails(
                since=last_check,
                unread_only=True,
                max_count=10,
            )
        except EmailAuthError:
            # Password salah / expired — opt-out + notifikasi user
            logger.warning(
                f"[Scheduler] {jid} auth failed — auto opt-out, notifying user"
            )
            await notify_opt_in_manager.disable(jid)
            if self._notify_callback:
                await self._notify_callback(
                    jid,
                    [],  # empty → callback akan handle sebagai error notif
                    error="auth_failed",
                )
            return
        except EmailConnectionError as e:
            # Server down / timeout — skip siklus ini, coba lagi nanti
            logger.warning(f"[Scheduler] {jid} connection error: {e} — will retry")
            return
        except Exception as e:
            logger.error(f"[Scheduler] Unexpected error for {jid}: {e}")
            return

        # Filter truly new
        truly_new = [e for e in new_emails if e.received_at > last_check]

        await self._set_last_check(jid, now)

        if truly_new:
            logger.info(
                f"[Scheduler] 🔔 {jid} → {len(truly_new)} new email(s)"
            )
            if self._notify_callback:
                try:
                    await self._notify_callback(jid, truly_new)
                except Exception as e:
                    logger.error(f"[Scheduler] Notify callback failed for {jid}: {e}")
        else:
            logger.debug(f"[Scheduler] {jid} → no new emails since {last_check:%H:%M}")


# Singleton
email_scheduler = MultiUserEmailScheduler(
    poll_interval_seconds=settings.email_poll_interval_seconds
)