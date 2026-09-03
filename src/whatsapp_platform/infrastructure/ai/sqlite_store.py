"""SQLite persistence module for AI chat configs and conversation history."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import structlog

from whatsapp_platform.features.ai.config_store import AIChatConfig
from whatsapp_platform.infrastructure.ai.interfaces import ProviderMessage

logger = structlog.get_logger()


class AISQLiteStore:
    """Async SQLite storage for per-chat AI configurations and LLM context cache."""

    def __init__(self, db_path: str = "./storage/ai_data.db") -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Connect to SQLite database and ensure tables exist."""
        if self._conn is not None:
            return

        if self.db_path != ":memory:":
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row

        if self.db_path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode=WAL;")

        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_config (
                chat_id TEXT PRIMARY KEY,
                ai_enabled BOOLEAN NOT NULL DEFAULT 0,
                model TEXT NULL,
                notice_sent BOOLEAN NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_chat_context_chat_id ON chat_context (chat_id);
            """
        )
        await self._conn.commit()
        logger.info("AISQLiteStore initialized", db_path=self.db_path)

    async def close(self) -> None:
        """Close SQLite database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Config Store operations
    # ------------------------------------------------------------------

    async def load_all_configs(self) -> dict[str, AIChatConfig]:
        """Load all chat configurations into memory."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        async with self._conn.execute(
            "SELECT chat_id, ai_enabled, model, notice_sent FROM chat_config"
        ) as cursor:
            rows = await cursor.fetchall()
            result: dict[str, AIChatConfig] = {}
            for row in rows:
                result[row["chat_id"]] = AIChatConfig(
                    enabled=bool(row["ai_enabled"]),
                    model=row["model"],
                    notice_sent=bool(row["notice_sent"]),
                )
            return result

    async def save_config(self, chat_id: str, config: AIChatConfig) -> None:
        """Upsert a single chat's AI configuration."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        sql = """
            INSERT INTO chat_config (chat_id, ai_enabled, model, notice_sent, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                ai_enabled=excluded.ai_enabled,
                model=excluded.model,
                notice_sent=excluded.notice_sent,
                updated_at=CURRENT_TIMESTAMP
        """
        await self._conn.execute(
            sql,
            (chat_id, 1 if config.enabled else 0, config.model, 1 if config.notice_sent else 0),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Context Cache operations
    # ------------------------------------------------------------------

    async def load_all_context(self) -> dict[str, list[ProviderMessage]]:
        """Load all LLM context history into memory grouped by chat_id."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        async with self._conn.execute(
            "SELECT chat_id, role, content FROM chat_context ORDER BY id ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            result: dict[str, list[ProviderMessage]] = {}
            for row in rows:
                chat_id = row["chat_id"]
                if chat_id not in result:
                    result[chat_id] = []
                result[chat_id].append(
                    ProviderMessage(role=row["role"], content=row["content"])
                )
            return result

    async def append_context_message(self, chat_id: str, message: ProviderMessage) -> None:
        """Persist a single context message to SQLite."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        sql = "INSERT INTO chat_context (chat_id, role, content) VALUES (?, ?, ?)"
        await self._conn.execute(sql, (chat_id, message.role, message.content))
        await self._conn.commit()

    async def delete_context_for_chat(self, chat_id: str) -> None:
        """Delete all context history rows for a specific chat_id (!ai reset)."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        await self._conn.execute("DELETE FROM chat_context WHERE chat_id = ?", (chat_id,))
        await self._conn.commit()

    async def trim_context_for_chat(self, chat_id: str, max_messages: int) -> None:
        """Trim history in SQLite keeping only the N most recent messages."""
        if not self._conn:
            raise RuntimeError("AISQLiteStore not initialized")
        sql = """
            DELETE FROM chat_context
            WHERE chat_id = ? AND id NOT IN (
                SELECT id FROM chat_context
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
        """
        await self._conn.execute(sql, (chat_id, chat_id, max_messages))
        await self._conn.commit()
