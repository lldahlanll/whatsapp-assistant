import asyncio
import json
import os
from datetime import datetime
from aiohttp import web
from loguru import logger

from app.memory.manager import memory_manager
from app.utils.stats import stats_tracker

HEALTH_PORT = int(os.getenv("HEALTH_PORT", 8080))


class HealthServer:
    """
    HTTP server untuk health check.
    
    Endpoints:
    GET /health  → status bot (UP/DOWN)
    GET /stats   → statistik harian
    GET /metrics → metrics singkat
    """

    def __init__(self, bot_ref):
        self.bot   = bot_ref
        self.app   = web.Application()
        self.start_time = datetime.now()
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/health",  self.handle_health)
        self.app.router.add_get("/stats",   self.handle_stats)
        self.app.router.add_get("/metrics", self.handle_metrics)

    async def handle_health(self, request):
        """GET /health — cek apakah bot dan Redis OK."""
        redis_ok = await memory_manager.ping()
        bot_ok   = bool(self.bot.bot_jid)

        status = "UP" if (redis_ok and bot_ok) else "DEGRADED"
        uptime = (datetime.now() - self.start_time).total_seconds()

        return web.Response(
            content_type="application/json",
            status=200 if status == "UP" else 503,
            text=json.dumps({
                "status"    : status,
                "bot_jid"   : self.bot.bot_jid or "not connected",
                "redis"     : "OK" if redis_ok else "FAIL",
                "uptime_sec": round(uptime),
                "timestamp" : datetime.now().isoformat(),
            }, indent=2),
        )

    async def handle_stats(self, request):
        """GET /stats — statistik harian lengkap."""
        summary = await stats_tracker.get_daily_summary()
        return web.Response(
            content_type="application/json",
            text=json.dumps(summary, indent=2),
        )

    async def handle_metrics(self, request):
        """GET /metrics — ringkasan singkat."""
        summary = await stats_tracker.get_daily_summary()
        return web.Response(
            content_type="application/json",
            text=json.dumps({
                "messages_today" : summary.get("messages_received", 0),
                "success_rate"   : summary.get("success_rate", 0),
                "active_users"   : summary.get("active_users", 0),
                "top_model"      : max(
                    summary.get("model_usage", {}).items(),
                    key=lambda x: x[1]["count"],
                    default=("none", {}),
                )[0],
            }, indent=2),
        )

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
        await site.start()
        logger.info(f"[Health] Server running on port {HEALTH_PORT}")