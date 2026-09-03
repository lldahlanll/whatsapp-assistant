"""ExponentialBackoffReconnector for auto-recovery.

Handles two distinct disconnect scenarios:
1. **Logged out from Android**: WhatsApp credentials are revoked.
   Reconnect attempts would fail immediately. Instead, we re-initiate
   pairing (gateway.connect) so a fresh QR code is presented without
   requiring a full process restart.
2. **Network / transient disconnect**: Normal exponential backoff reconnect.
"""

import asyncio

import structlog

from whatsapp_platform.application.interfaces.messaging_gateway import IMessagingGateway
from whatsapp_platform.domain.events.session_events import SessionDisconnected
from whatsapp_platform.domain.repositories.session_repository import ISessionRepository

logger = structlog.get_logger()

# Neonize/Whatsmeow fires a dedicated LoggedOutEv (event code 6) when the phone
# revokes the session. Our gateway explicitly maps this to reason="loggedout".
# This is distinct from DisconnectedEv (code 12) which is a transient disconnect.
_LOGOUT_REASON = "loggedout"


def _is_logout(reason: str) -> bool:
    """Return True if the disconnect reason indicates the session was revoked."""
    return reason == _LOGOUT_REASON


class ExponentialBackoffReconnector:
    def __init__(
        self,
        gateway: IMessagingGateway,
        session_repo: ISessionRepository,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        max_attempts: int = 5,
    ) -> None:
        self.gateway = gateway
        self.session_repo = session_repo
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts

    async def on_disconnected(self, event: SessionDisconnected) -> None:
        logger.warning(
            "Session disconnected, starting reconnect handler",
            session_id=event.session_id,
            reason=event.reason,
        )
        session = await self.session_repo.get_by_id(event.session_id)
        if not session:
            return

        # ------------------------------------------------------------------
        # Case 1: User logged out from Android → re-initiate pairing (new QR)
        # ------------------------------------------------------------------
        if _is_logout(event.reason):
            logger.warning(
                "Session was logged out remotely — re-initiating pairing for new QR code",
                session_id=event.session_id,
                reason=event.reason,
            )
            try:
                session.disconnect()
                await self.session_repo.save(session)
                # Calling connect() will restart the Neonize client and cause
                # WhatsApp to emit a fresh QRCodeGenerated event automatically.
                await self.gateway.connect()
                logger.info("Re-pairing initiated — waiting for new QR code scan")
            except Exception as exc:
                logger.error(
                    "Failed to re-initiate pairing after logout",
                    error=str(exc),
                    exc_info=True,
                )
                session.fail(reason=f"Logout re-pair failed: {exc}")
                await self.session_repo.save(session)
            return

        # ------------------------------------------------------------------
        # Case 2: Transient disconnect (network, server blip) → backoff retry
        # ------------------------------------------------------------------
        attempts = 0
        while attempts < self.max_attempts:
            attempts += 1
            delay = min(self.base_delay * (2 ** (attempts - 1)), self.max_delay)
            logger.info(
                "Attempting auto-reconnect", attempt=attempts, delay_seconds=delay
            )
            await asyncio.sleep(delay)

            try:
                session.start_reconnect()
                await self.session_repo.save(session)
                await self.gateway.connect()

                if await self.gateway.is_connected():
                    session.connect()
                    await self.session_repo.save(session)
                    logger.info("Auto-reconnect successful!")
                    return
            except Exception as exc:
                logger.error(
                    "Auto-reconnect attempt failed", attempt=attempts, error=str(exc), exc_info=True
                )

        session.fail(reason=f"Failed to reconnect after {self.max_attempts} attempts")
        await self.session_repo.save(session)
