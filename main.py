import asyncio
import signal
import sys
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from app.bot import WhatsAppBot
from app.ai.client import openrouter_client
from app.memory.manager import memory_manager
from app.utils.logger import setup_logger
from app.utils.stats import stats_tracker

setup_logger()


async def main():
    logger.info("[Main] ══════════════════════════════════")
    logger.info("[Main]      WhatsApp AI Bot Starting     ")
    logger.info("[Main]   Neonize 0.3.x + Python 3.12    ")
    logger.info("[Main] ══════════════════════════════════")

    bot = WhatsAppBot()

    # Import health server di sini supaya bot_ref bisa dipass
    from app.utils.health import HealthServer
    health = HealthServer(bot_ref=bot)

    async def shutdown():
        logger.info("[Main] Shutting down gracefully...")
        await openrouter_client.close()
        await memory_manager.close()
        await stats_tracker.close()
        logger.info("[Main] All connections closed. Goodbye!")
        sys.exit(0)

    # Handle Ctrl+C
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown())
        )

    # Jalankan health server & bot bersamaan
    asyncio.create_task(health.start())
    # await asyncio.gather(
    #     await bot.start(),
    #     bot.start(),
    # )
    try:
        await bot.start()
    except Exception as e:
        logger.critical(f"[Main] Bot failed to start: {e}")
    


if __name__ == "__main__":
    asyncio.run(main())