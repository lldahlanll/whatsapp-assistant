"""QRDisplayHandler — renders WhatsApp QR codes on the CLI terminal.

WhatsApp sends a new QREv every ~60 seconds if the QR has not been scanned.
This handler is subscribed to QRCodeGenerated and will re-render the QR
automatically each time a new one arrives — no special expiry logic needed.
"""

import segno
import structlog
import structlog.contextvars

from whatsapp_platform.domain.events.session_events import QRCodeGenerated

logger = structlog.get_logger()

_QR_BORDER = "=" * 54
_QR_VALID_SECONDS = 60


class QRDisplayHandler:
    @staticmethod
    async def on_qr_generated(event: QRCodeGenerated) -> None:
        """Render a QR code to the terminal for WhatsApp pairing.

        Called every time Neonize sends a new QREv.  WhatsApp generates a
        fresh QR every ~60 s, so repeated calls are expected until the user
        scans the code.
        """
        # Bind session context to structured log entries
        structlog.contextvars.bind_contextvars(session_id=event.session_id)
        logger.info("Displaying QR Code for pairing — scan within 60 seconds")

        try:
            qr = segno.make_qr(event.qr_code)

            print(f"\n{_QR_BORDER}")
            print("  📱 SCAN THIS QR CODE WITH WHATSAPP ON YOUR PHONE  ")
            print(
                f"  ⏱  QR valid for ~{_QR_VALID_SECONDS} seconds. A new one will appear if expired."
            )
            print(_QR_BORDER)
            qr.terminal(compact=True)
            print(_QR_BORDER + "\n")

        except Exception as exc:
            logger.error("Failed to render QR Code on terminal", error=str(exc), exc_info=True)
            print(f"\n[QR Code Raw — paste into a QR generator]: {event.qr_code}\n")
        finally:
            structlog.contextvars.unbind_contextvars("session_id")
