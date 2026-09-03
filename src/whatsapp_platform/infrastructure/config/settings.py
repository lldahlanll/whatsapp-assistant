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
    debug: bool = Field(default=True, description="Enable debug logging")

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
    api_host: str = Field(default="0.0.0.0", description="API server bind host")  # noqa: S104
    api_port: int = Field(default=8000, description="API server port")
    api_key: str = Field(default="", description="API key for X-API-Key authentication (empty = disabled)")

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

    ai_cooldown_default_seconds: float = Field(
        default=60.0, description="Default key cooldown when Retry-After is absent"
    )
    ai_rate_limit_max_requests: int = Field(
        default=5, description="Max AI requests per minute per chat"
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
    ai_bot_mention_name: str = Field(
        default="", description="Bot display name for group chat @mention detection"
    )
    ai_http_timeout_seconds: float = Field(
        default=30.0, description="HTTP timeout for AI provider client"
    )
    ai_database_path: str = Field(
        default="./storage/ai_data.db", description="Path to AI persistence SQLite database"
    )

    # Customer Lookup MySQL settings
    mysql_host: str = Field(default="", description="MySQL Host")
    mysql_port: int = Field(default=3306, description="MySQL Port")
    mysql_user: str = Field(default="", description="MySQL User")
    mysql_password: str = Field(default="", description="MySQL Password")
    mysql_db: str = Field(default="", description="MySQL Database")
    mysql_pool_min_size: int = Field(default=1, description="MySQL Pool minimum size")
    mysql_pool_max_size: int = Field(default=3, description="MySQL Pool maximum size")
    mysql_query_timeout_ms: int = Field(default=3000, description="MySQL query timeout in milliseconds")
    customer_lookup_allowed_groups: list[str] | str = Field(
        default_factory=list, description="Allowed WhatsApp group JIDs for Customer Lookup"
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
        "customer_lookup_allowed_groups",
        "network_allowed_jids",
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


