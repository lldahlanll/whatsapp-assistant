# main.py
import asyncio
import signal
import sys

from dotenv import load_dotenv

# Load .env SEBELUM import modul yang baca config
load_dotenv()

from app.ai.client import multi_client  # noqa: E402
from app.bot import WhatsAppBot  # noqa: E402
from app.memory.manager import memory_manager  # noqa: E402
from app.utils.health import HealthServer  # noqa: E402
from app.utils.logger import setup_logger  # noqa: E402
from app.utils.stats import stats_tracker  # noqa: E402
from loguru import logger  # noqa: E402

setup_logger()


async def main() -> None:
    logger.info("[Main] ══════════════════════════════════")
    logger.info("[Main]      WhatsApp AI Bot Starting     ")
    logger.info("[Main]   Neonize 0.3.x + Python 3.12     ")
    logger.info("[Main] ══════════════════════════════════")

    bot = WhatsAppBot()
    health = HealthServer(bot_ref=bot)
    stop_event = asyncio.Event()

    # Signal handlers
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            logger.info("[Main] Signal received, initiating shutdown...")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows fallback
            signal.signal(sig, lambda *_: _request_shutdown())

    # Start services
    health_task = asyncio.create_task(health.start(), name="health")
    bot_task = asyncio.create_task(bot.start(), name="bot")

    # Tunggu sampai shutdown signal ATAU bot crash
    stop_task = asyncio.create_task(stop_event.wait(), name="stop_signal")
    done, pending = await asyncio.wait(
        [bot_task, stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if bot_task in done:
        try:
            bot_task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.critical(f"[Main] Bot crashed: {e}")
    else:
        bot_task.cancel()

    logger.info("[Main] Cleaning up...")
    await bot.stop()

    health_task.cancel()
    await asyncio.gather(
        health.stop(),
        bot_task,
        health_task,
        return_exceptions=True,
    )

    await asyncio.gather(
        multi_client.close(),
        memory_manager.close(),
        stats_tracker.close(),
        return_exceptions=True,
    )

    logger.info("[Main] Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)