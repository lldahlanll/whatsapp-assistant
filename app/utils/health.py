# app/utils/health.py
import json
from datetime import datetime

from aiohttp import web
from loguru import logger

from app.config import settings
from app.memory.manager import memory_manager
from app.utils.stats import stats_tracker


class HealthServer:
    def __init__(self, bot_ref) -> None:
        self.bot = bot_ref
        self.app = web.Application()
        self.start_time = datetime.now()
        self._runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health",   self.handle_health)
        self.app.router.add_get("/stats",    self.handle_stats)
        self.app.router.add_get("/metrics",  self.handle_metrics)
        self.app.router.add_get("/locks",    self.handle_locks)
        self.app.router.add_get("/breakers", self.handle_breakers)  # NEW

    async def handle_health(self, request: web.Request) -> web.Response:
        redis_ok = await memory_manager.ping()
        bot_ok = bool(self.bot.bot_jid)
        status = "UP" if (redis_ok and bot_ok) else "DEGRADED"
        uptime = (datetime.now() - self.start_time).total_seconds()

        return web.json_response(
            {
                "status": status,
                "bot_jid": self.bot.bot_jid or "not connected",
                "redis": "OK" if redis_ok else "FAIL",
                "uptime_sec": round(uptime),
                "timestamp": datetime.now().isoformat(),
            },
            status=200 if status == "UP" else 503,
        )

    async def handle_locks(self, request: web.Request) -> web.Response:
        from app.utils.locks import jid_lock_manager
        return web.json_response(jid_lock_manager.stats())

    async def handle_breakers(self, request: web.Request) -> web.Response:
        """
        GET /breakers — lihat circuit breaker status semua model.

        Response example:
        {
          "disabled_count": 2,
          "models": {
            "gemini-acc1:gemini-2.5-pro": {
              "remaining_sec": 42300,
              "remaining_human": "11h 45m",
              "reason": "HTTP 429 (quota)",
              "duration_total": 43200
            }
          }
        }

        Juga support POST /breakers/reset?key=... untuk reset manual.
        """
        from app.ai.client import multi_client
        breaker_data = await multi_client.breaker_status()
        return web.json_response({
            "disabled_count": len(breaker_data),
            "models": breaker_data,
        })

    async def handle_stats(self, request: web.Request) -> web.Response:
        return web.json_response(await stats_tracker.get_daily_summary())

    async def handle_metrics(self, request: web.Request) -> web.Response:
        summary = await stats_tracker.get_daily_summary()
        top_model = max(
            summary.get("model_usage", {}).items(),
            key=lambda x: x[1]["count"],
            default=("none", {}),
        )[0]

        return web.json_response({
            "messages_today":  summary.get("messages_received", 0),
            "success_rate":    summary.get("success_rate", 0),
            "active_users":    summary.get("active_users", 0),
            "top_model":       top_model,
        })

    async def start(self) -> None:
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", settings.health_port)
        await site.start()
        logger.info(f"[Health] Server running on port {settings.health_port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()