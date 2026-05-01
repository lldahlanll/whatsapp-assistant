# app/config.py
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
    circuit_breaker_disable_duration: int = 600

    # ── Redis ─────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ── Memory ────────────────────────────────────────────────
    max_history_messages: int = 20
    history_ttl_seconds: int = 7 * 24 * 60 * 60

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

    # ── Email / Zimbra (FALLBACK / shared mode) ───────────────
    # Note: kalau multi-user mode aktif, ini hanya dipakai sebagai
    # template hostname (IMAP_HOST, IMAP_PORT, dll) untuk semua user.
    # Username & password per user disimpan di credential store.
    imap_host: Optional[str] = None
    imap_port: int = 993
    smtp_host: Optional[str] = None
    smtp_port: int = 465
    email_username: Optional[str] = None  # legacy: single-user mode
    email_password: Optional[str] = None  # legacy: single-user mode
    email_sender_name: Optional[str] = None
    email_notify_jid: Optional[str] = None
    email_poll_interval_seconds: int = 300

    # ── Multi-User Auth ───────────────────────────────────────
    # Master key untuk encrypt password — WAJIB untuk multi-user mode
    auth_master_key: Optional[str] = None

    # Admin JIDs (comma-separated)
    # Format: 628aaa@s.whatsapp.net,628bbb@s.whatsapp.net
    admin_jids: Optional[str] = None

    # Multi-user mode toggle
    # False = single-user (pakai EMAIL_USERNAME/PASSWORD dari .env)
    # True  = multi-user (per-user credentials via /login)
    multi_user_mode: bool = False

    # Session TTL (default 8 jam)
    auth_session_ttl_seconds: int = 8 * 60 * 60

    # ── Computed properties ───────────────────────────────────
    @property
    def session_db_path(self) -> str:
        return self.db_path or f"data/sessions/{self.session_name}.db"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def email_configured(self) -> bool:
        """Single-user mode: cek kredensial di .env."""
        return all([
            self.imap_host,
            self.smtp_host,
            self.email_username,
            self.email_password,
        ])

    @property
    def multi_user_configured(self) -> bool:
        """Multi-user mode: cek master key dan host config."""
        return all([
            self.multi_user_mode,
            self.auth_master_key,
            self.imap_host,
            self.smtp_host,
        ])

    @property
    def configured_providers(self) -> dict[str, bool]:
        return {
            "groq":         bool(self.groq_api_key),
            "gemini_1":     bool(self.gemini_api_key_1),
            "gemini_2":     bool(self.gemini_api_key_2),
            "openrouter_1": bool(self.openrouter_api_key_1),
            "openrouter_2": bool(self.openrouter_api_key_2),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()