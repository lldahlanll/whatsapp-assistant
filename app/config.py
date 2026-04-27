from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Provider API Keys ─────────────────────────────────────
    # Semua optional — endpoint dengan key None akan di-skip saat registrasi
    groq_api_key: Optional[str] = None
    gemini_api_key_1: Optional[str] = None
    gemini_api_key_2: Optional[str] = None
    openrouter_api_key_1: Optional[str] = None
    openrouter_api_key_2: Optional[str] = None

    # ── Provider Base URLs ────────────────────────────────────
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── HTTP & Reliability ────────────────────────────────────
    request_timeout: float = 60.0
    max_retries: int = 2
    retry_delay: float = 1.5

    # ── Circuit Breaker ───────────────────────────────────────
    circuit_breaker_disable_duration: int = 600  # 10 menit

    # ── Redis ─────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ── Memory ────────────────────────────────────────────────
    max_history_messages: int = 20
    history_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 hari

    # ── Rate Limiter ──────────────────────────────────────────
    rate_limit_max: int = 5
    rate_limit_window_seconds: int = 10

    # ── Bot ───────────────────────────────────────────────────
    bot_name: str = "Ephinu Bot"
    session_name: str = "bot_session"
    db_path: Optional[str] = None

    # ── Stats ─────────────────────────────────────────────────
    stats_ttl_seconds: int = 7 * 24 * 60 * 60

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Health Server ─────────────────────────────────────────
    health_port: int = 8080

    # ── Computed properties ───────────────────────────────────
    @property
    def session_db_path(self) -> str:
        return self.db_path or f"data/sessions/{self.session_name}.db"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def configured_providers(self) -> dict[str, bool]:
        """Untuk debugging: cek key mana yang sudah diisi."""
        return {
            "groq": bool(self.groq_api_key),
            "gemini_1": bool(self.gemini_api_key_1),
            "gemini_2": bool(self.gemini_api_key_2),
            "openrouter_1": bool(self.openrouter_api_key_1),
            "openrouter_2": bool(self.openrouter_api_key_2),
        }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — dipanggil di seluruh app."""
    return Settings()


settings = get_settings()