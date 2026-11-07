"""Configuration Settings using Pydantic-Settings."""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="whatsapp-platform", description="Application name")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Execution environment"
    )
    debug: bool = Field(default=False, description="Enable debug logging")

    session_name: str = Field(
        default="default_session", description="WhatsApp Session Identifier"
    )
    pairing_method: Literal["qr", "code"] = Field(
        default="qr", description="Authentication pairing method ('qr' or 'code')"
    )
    pairing_phone_number: str = Field(
        default="", description="Target phone number when PAIRING_METHOD='code'"
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./storage/session.db",
        description="Database connection URL",
    )

    command_prefix: str = Field(default="!", description="Bot command prefix")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Log level"
    )

    # REST API settings
    api_enabled: bool = Field(default=True, description="Enable REST API server")
    api_host: str = Field(
        default="127.0.0.1",
        description="API server bind host (pakai 0.0.0.0 hanya di dalam container / di belakang reverse proxy)",
    )
    api_port: int = Field(default=8000, description="API server port")
    api_key: str = Field(default="", description="API key for X-API-Key authentication (empty = disabled)")
    api_docs_enabled: bool = Field(
        default=False, description="Buka /docs, /redoc dan /openapi.json (jangan aktifkan di production)"
    )
    api_cors_origins: list[str] | str = Field(
        default_factory=list,
        description="Origin yang boleh akses API dari browser (comma-separated). Kosong = CORS mati",
    )

    # AI Multi-Provider settings
    gemini_api_keys: list[str] | str = Field(
        default_factory=list, description="Gemini API key list (comma-separated)"
    )
    groq_api_keys: list[str] | str = Field(
        default_factory=list, description="Groq API key list (comma-separated)"
    )
    openrouter_api_keys: list[str] | str = Field(
        default_factory=list, description="OpenRouter API key list (comma-separated)"
    )

    # 9router settings
    ninerouter_api_keys: list[str] | str = Field(
        default_factory=list,
        description="9router API key list (comma-separated)",
    )
    ninerouter_base_url: str = Field(
        default="",
        description="9router base URL, e.g. http://localhost:4000/v1",
    )
    ninerouter_model_chat: str = Field(
        default="chat-pool",
        description="Virtual model name for chat intent in 9router",
    )
    ninerouter_model_tools: str = Field(
        default="tools-pool",
        description="Virtual model name for finance/network tool calling intent in 9router",
    )
    ninerouter_model_vision: str = Field(
        default="vision-pool",
        description="Virtual model name for image/vision intent in 9router",
    )

    ai_cooldown_default_seconds: float = Field(
        default=60.0, description="Default key cooldown when Retry-After is absent"
    )
    ai_rate_limit_max_requests: int = Field(
        default=5, description="Max AI requests per minute per chat"
    )
    ai_rate_limit_per_user_max_requests: int = Field(
        default=3, description="Max AI requests per window per pengirim di grup (0 = nonaktif)"
    )
    ai_rate_limit_window_seconds: float = Field(
        default=60.0, description="Per-chat rate guard window in seconds"
    )
    ai_context_window_messages: int = Field(
        default=10, description="Max messages included in LLM context"
    )
    ai_chat_history_limit: int = Field(
        default=3, description="History message count for chat intent"
    )
    ai_finance_history_limit: int = Field(
        default=5, description="History message count for finance intent"
    )
    ai_network_history_limit: int = Field(
        default=3, description="History message count for network intent"
    )
    ai_complex_history_limit: int = Field(
        default=8, description="History message count for complex/full intent"
    )
    ai_max_tool_result_chars: int = Field(
        default=1000, description="Max character budget for compact tool result"
    )
    ai_max_tool_iterations: int = Field(
        default=3, description="Max tool iterations in agentic loop"
    )
    ai_max_context_chars: int = Field(
        default=16000, description="Max character budget for LLM context"
    )
    ai_default_enabled: bool = Field(
        default=False,
        description="Aktifkan AI otomatis untuk chat baru. Default mati; nyalakan per chat lewat !ai on",
    )
    ai_admin_jids: list[str] | str = Field(
        default_factory=list,
        description="Nomor/JID yang boleh menjalankan !ai on/off/reset/model/stats (comma-separated)",
    )
    ai_bot_mention_name: str = Field(
        default="", description="Bot display name for group chat @mention detection"
    )
    ai_http_timeout_seconds: float = Field(
        default=30.0, description="HTTP timeout for AI provider client"
    )
    ai_vision_enabled: bool = Field(
        default=True, description="Analisis gambar (vision) untuk pesan gambar yang memicu AI"
    )
    ai_image_max_bytes: int = Field(
        default=5 * 1024 * 1024,
        description="Ukuran maksimum gambar (byte) yang diunduh dan dikirim ke model vision",
    )
    ai_database_path: str = Field(
        default="./storage/ai_data.db", description="Path to AI persistence SQLite database"
    )
    ai_memory_enabled: bool = Field(
        default=True,
        description="Memori persisten per pengguna: fakta yang diminta diingat disuntikkan ke system prompt",
    )
    ai_memory_max_entries: int = Field(
        default=20, description="Jumlah maksimum catatan memori per pengguna per chat"
    )
    ai_memory_max_chars: int = Field(
        default=1500, description="Total karakter maksimum memori per pengguna per chat"
    )
    scheduler_enabled: bool = Field(
        default=True,
        description="Pengingat & laporan terjadwal yang dikirim bot secara proaktif",
    )
    scheduler_poll_seconds: float = Field(
        default=20.0, ge=5.0, le=300.0, description="Interval (detik) pengecekan jadwal jatuh tempo"
    )
    ai_voice_enabled: bool = Field(
        default=True,
        description="Transkripsi voice note (Groq Whisper) lalu diproses seperti pesan teks",
    )
    ai_audio_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Ukuran maksimum voice note (byte) yang diunduh dan ditranskripsi",
    )
    ai_audio_max_seconds: int = Field(
        default=180, description="Durasi maksimum voice note (detik) yang ditranskripsi"
    )
    ai_transcription_model: str = Field(
        default="whisper-large-v3-turbo", description="Model transkripsi Groq Whisper"
    )
    ai_transcription_language: str = Field(
        default="id", description="Kode bahasa ISO-639-1 untuk transkripsi (kosong = deteksi otomatis)"
    )

    # MikroTik REST API & Network AI settings
    mikrotik_enabled: bool = Field(default=False, description="Enable MikroTik integration")
    mikrotik_host: str = Field(default="", description="MikroTik Router IP or Hostname")
    mikrotik_port: int = Field(default=80, description="MikroTik REST API Port (80 for HTTP, 443 for HTTPS)")
    mikrotik_username: str = Field(default="", description="MikroTik Username")
    mikrotik_password: str = Field(default="", description="MikroTik Password")
    mikrotik_use_ssl: bool = Field(default=False, description="Use HTTPS for MikroTik REST API")
    mikrotik_verify_ssl: bool = Field(default=False, description="Verify SSL certificate for HTTPS")
    mikrotik_timeout: float = Field(default=5.0, description="MikroTik API request timeout in seconds")
    network_allowed_jids: list[str] | str = Field(
        default_factory=list, description="Allowed WhatsApp JIDs (users/groups) for Network AI commands"
    )
    network_cache_ttl_system: int = Field(default=30, description="Cache TTL for system health in seconds")
    network_cache_ttl_firewall: int = Field(default=60, description="Cache TTL for firewall rules in seconds")
    network_cache_ttl_routes: int = Field(default=30, description="Cache TTL for routes in seconds")
    network_cache_ttl_dhcp: int = Field(default=15, description="Cache TTL for DHCP leases in seconds")


    @field_validator(
        "gemini_api_keys",
        "groq_api_keys",
        "openrouter_api_keys",
        "ninerouter_api_keys",
        "network_allowed_jids",
        "ai_admin_jids",
        "api_cors_origins",
        mode="before",
    )
    @classmethod
    def _parse_keys_list(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            if not value.strip():
                return []
            return [k.strip() for k in value.split(",") if k.strip()]
        return value

    def mikrotik_security_warnings(self) -> list[str]:
        """Peringatan konfigurasi MikroTik yang berisiko (kredensial router lewat jaringan)."""
        if not (self.mikrotik_enabled and self.mikrotik_host):
            return []
        warnings: list[str] = []
        if not self.mikrotik_use_ssl:
            warnings.append(
                "MIKROTIK_USE_SSL=false: kredensial router dikirim cleartext (HTTP Basic Auth). "
                "Aktifkan www-ssl di RouterOS dan set MIKROTIK_USE_SSL=true."
            )
        elif not self.mikrotik_verify_ssl:
            warnings.append(
                "MIKROTIK_VERIFY_SSL=false: sertifikat router tidak diverifikasi (rentan MITM). "
                "Pasang sertifikat valid/CA sendiri lalu set MIKROTIK_VERIFY_SSL=true."
            )
        return warnings

    @field_validator("mikrotik_enabled", mode="before")
    @classmethod
    def _parse_bool(cls, value: Any) -> bool:
        if isinstance(value, str):
            clean = value.strip().lower()
            if clean in ("enable", "enabled", "true", "1", "yes", "on"):
                return True
            if clean in ("disable", "disabled", "false", "0", "no", "off"):
                return False
        return bool(value)


