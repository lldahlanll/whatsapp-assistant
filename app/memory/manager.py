import json
import time
import os
from typing import Optional
from loguru import logger
import redis.asyncio as aioredis

# ── Config ────────────────────────────────────────────────────
REDIS_HOST          = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT          = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB            = int(os.getenv("REDIS_DB", 0))
MAX_HISTORY         = int(os.getenv("MAX_HISTORY_MESSAGES", 20))

# TTL (Time To Live) — history otomatis expired setelah 7 hari tidak aktif
HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60   # 7 hari

# System prompt default untuk semua percakapan
SYSTEM_PROMPT = """Kamu adalah asisten AI yang membantu dan ramah, 
diintegrasikan ke WhatsApp. Jawab dalam bahasa yang sama dengan 
yang digunakan user. Jawab secara ringkas dan jelas. 
Jangan menyebut dirimu sebagai model AI tertentu."""


class MemoryManager:
    """
    Kelola riwayat percakapan per user/group menggunakan Redis.

    Setiap JID (WhatsApp ID) punya history-nya sendiri.
    History disimpan sebagai Redis List dengan format JSON per item.

    JID format:
      - Private : 628xxx@s.whatsapp.net
      - Group   : 120363xxx@g.us
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy init Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info(
                f"[Memory] Redis connected → "
                f"{REDIS_HOST}:{REDIS_PORT}/db{REDIS_DB}"
            )
        return self._redis

    async def close(self):
        """Tutup koneksi Redis saat bot shutdown."""
        if self._redis:
            await self._redis.aclose()
            logger.info("[Memory] Redis connection closed.")

    # ── Key Builders ──────────────────────────────────────────

    def _history_key(self, jid: str) -> str:
        return f"history:{jid}"

    def _meta_key(self, jid: str) -> str:
        return f"meta:{jid}"

    # ── Core: Add Message ─────────────────────────────────────

    async def add_message(
        self,
        jid: str,
        role: str,           # "user" atau "assistant"
        content: str,
    ) -> None:
        """
        Tambah satu pesan ke history.
        Otomatis trim jika melebihi MAX_HISTORY.
        Refresh TTL setiap ada activity.

        Args:
            jid     : WhatsApp ID (user atau group)
            role    : "user" atau "assistant"
            content : Isi pesan
        """
        try:
            r = await self._get_redis()
            key = self._history_key(jid)

            message = {
                "role": role,
                "content": content,
                "timestamp": int(time.time()),
            }

            # Tambah ke ujung list (RPUSH = Right Push)
            await r.rpush(key, json.dumps(message, ensure_ascii=False))

            # Trim — hanya simpan MAX_HISTORY pesan terakhir
            # LTRIM key 0 (MAX_HISTORY-1) = simpan dari index 0 sampai N-1
            await r.ltrim(key, -MAX_HISTORY, -1)

            # Refresh TTL setiap ada aktivitas
            await r.expire(key, HISTORY_TTL_SECONDS)

            logger.debug(f"[Memory] Added '{role}' message for {jid}")

        except Exception as e:
            # Memory error tidak boleh crash bot
            logger.error(f"[Memory] Failed to add message for {jid}: {e}")

    # ── Core: Get History ─────────────────────────────────────

    async def get_history(self, jid: str) -> list[dict]:
        """
        Ambil semua history percakapan untuk dikirim ke AI.

        Returns format siap pakai untuk OpenRouter API:
        [
            {"role": "system",    "content": "..."},
            {"role": "user",      "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
        """
        try:
            r = await self._get_redis()
            key = self._history_key(jid)

            # Ambil semua item dari list
            raw_messages = await r.lrange(key, 0, -1)

            if not raw_messages:
                # Belum ada history → return hanya system prompt
                return [{"role": "system", "content": SYSTEM_PROMPT}]

            # Parse JSON setiap item, buang field "timestamp"
            # (timestamp hanya untuk internal, tidak dikirim ke AI)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for raw in raw_messages:
                try:
                    msg = json.loads(raw)
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })
                except json.JSONDecodeError:
                    # Skip pesan yang corrupt
                    logger.warning(f"[Memory] Corrupt message in {jid}, skipping")
                    continue

            logger.debug(
                f"[Memory] Loaded {len(messages)-1} messages for {jid}"
            )
            return messages

        except Exception as e:
            logger.error(f"[Memory] Failed to get history for {jid}: {e}")
            # Fallback — kembalikan hanya system prompt
            return [{"role": "system", "content": SYSTEM_PROMPT}]

    # ── Core: Clear History ───────────────────────────────────

    async def clear_history(self, jid: str) -> bool:
        """
        Hapus semua history untuk JID tertentu.
        Dipanggil saat user kirim command /reset.

        Returns:
            True jika berhasil, False jika gagal
        """
        try:
            r = await self._get_redis()
            deleted = await r.delete(
                self._history_key(jid),
                self._meta_key(jid),
            )
            logger.info(f"[Memory] Cleared history for {jid} ({deleted} keys)")
            return True
        except Exception as e:
            logger.error(f"[Memory] Failed to clear history for {jid}: {e}")
            return False

    # ── Meta: Simpan Info User/Group ──────────────────────────

    async def save_meta(
        self,
        jid: str,
        name: str,
        is_group: bool,
    ) -> None:
        """
        Simpan metadata user/group (nama, tipe).
        Berguna untuk logging dan personalisasi response.
        """
        try:
            r = await self._get_redis()
            meta = {
                "name": name,
                "is_group": is_group,
                "last_seen": int(time.time()),
            }
            await r.set(
                self._meta_key(jid),
                json.dumps(meta, ensure_ascii=False),
                ex=HISTORY_TTL_SECONDS,
            )
        except Exception as e:
            logger.error(f"[Memory] Failed to save meta for {jid}: {e}")

    async def get_meta(self, jid: str) -> Optional[dict]:
        """Ambil metadata user/group."""
        try:
            r = await self._get_redis()
            raw = await r.get(self._meta_key(jid))
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"[Memory] Failed to get meta for {jid}: {e}")
            return None

    # ── Stats ─────────────────────────────────────────────────

    async def get_stats(self, jid: str) -> dict:
        """
        Ambil statistik history untuk JID tertentu.
        Berguna untuk command /stats atau debugging.
        """
        try:
            r = await self._get_redis()
            key = self._history_key(jid)

            count = await r.llen(key)
            ttl   = await r.ttl(key)

            return {
                "jid": jid,
                "message_count": count,
                "max_history": MAX_HISTORY,
                "ttl_seconds": ttl,
                "ttl_hours": round(ttl / 3600, 1) if ttl > 0 else 0,
            }
        except Exception as e:
            logger.error(f"[Memory] Failed to get stats for {jid}: {e}")
            return {}

    # ── Health Check ──────────────────────────────────────────

    async def ping(self) -> bool:
        """Test koneksi Redis — return True jika OK."""
        try:
            r = await self._get_redis()
            result = await r.ping()
            return result is True
        except Exception:
            return False


# ── Singleton instance ─────────────────────────────────────────
memory_manager = MemoryManager()