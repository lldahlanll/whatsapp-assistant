"""StatusCommandHandler — responds with system health, memory, and uptime status."""

import os
import platform
import time
from datetime import UTC, datetime

import structlog

from whatsapp_platform.features.commands.base import BaseCommandHandler
from whatsapp_platform.features.commands.context import CommandContext

logger = structlog.get_logger()

_START_TIME = time.time()


class StatusCommandHandler(BaseCommandHandler):
    """Handler for '!status' command."""

    @property
    def command_name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "Menampilkan status kesehatan sistem, uptime, dan memori platform."

    async def handle(self, ctx: CommandContext) -> None:
        uptime_seconds = int(time.time() - _START_TIME)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}j {minutes}m {seconds}s"

        # Memory usage info
        mem_info_str = "N/A"
        try:
            import psutil  # type: ignore[import-untyped]

            process = psutil.Process(os.getpid())

            mem_bytes = process.memory_info().rss
            mem_mb = mem_bytes / (1024 * 1024)
            mem_info_str = f"{mem_mb:.1f} MB"
        except ImportError:
            mem_info_str = "psutil tidak terinstall"
        except Exception as exc:
            logger.debug("Could not get memory usage via psutil", error=str(exc))

        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        status_text = (
            "📊 *WHATSAPP PLATFORM STATUS*\n"
            "-----------------------------------\n"
            f"🟢 *Status*: ACTIVE / ONLINE\n"
            f"⏱ *Uptime*: {uptime_str}\n"
            f"💾 *Memory Usage*: {mem_info_str}\n"
            f"🐍 *Python Version*: {platform.python_version()}\n"
            f"💻 *OS*: {platform.system()} {platform.release()}\n"
            f"🕒 *Server Time*: {now_utc}\n"
            "-----------------------------------"
        )

        logger.info("Executing !status command", chat=str(ctx.message.chat_jid))
        await ctx.reply(status_text)
