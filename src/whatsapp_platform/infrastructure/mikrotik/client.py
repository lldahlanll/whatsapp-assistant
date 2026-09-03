"""MikroTik REST API Client for RouterOS v7.

Strictly READ-ONLY client for querying RouterOS REST endpoints.
Never exposes write, update, delete, or arbitrary script execution capabilities.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from whatsapp_platform.infrastructure.config.settings import Settings
from whatsapp_platform.infrastructure.mikrotik.exceptions import (
    MikroTikAuthError,
    MikroTikConnectionError,
    MikroTikDisabledError,
    MikroTikError,
    MikroTikTimeoutError,
)

logger = structlog.get_logger()


class MikroTikRestClient:
    """Read-only async client for RouterOS v7 REST API."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._custom_client = http_client
        self._internal_client: httpx.AsyncClient | None = None

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.mikrotik_enabled and self._settings.mikrotik_host)

    @property
    def base_url(self) -> str:
        protocol = "https" if self._settings.mikrotik_use_ssl else "http"
        host = self._settings.mikrotik_host
        port = self._settings.mikrotik_port
        return f"{protocol}://{host}:{port}/rest"

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client

        if self._internal_client is None or self._internal_client.is_closed:
            self._internal_client = httpx.AsyncClient(
                verify=self._settings.mikrotik_verify_ssl,
                timeout=httpx.Timeout(self._settings.mikrotik_timeout),
                auth=(self._settings.mikrotik_username, self._settings.mikrotik_password),
            )
        return self._internal_client

    async def aclose(self) -> None:
        """Close internal HTTP client session if opened."""
        if self._internal_client is not None and not self._internal_client.is_closed:
            await self._internal_client.aclose()
            self._internal_client = None

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]] | dict[str, Any]:
        """Perform a read-only GET request to RouterOS REST API.

        Args:
            endpoint: REST path e.g. "system/resource", "interface", "ip/firewall/filter"
            params: Optional query parameters for filtering / pagination

        Returns:
            Parsed JSON result from MikroTik RouterOS

        Raises:
            MikroTikDisabledError: When integration is not enabled
            MikroTikAuthError: When credentials or permissions fail (401/403)
            MikroTikTimeoutError: When request exceeds timeout
            MikroTikConnectionError: On network or DNS failure
            MikroTikError: On other API failures
        """
        if not self.is_enabled:
            raise MikroTikDisabledError("MikroTik integration is disabled or host is not configured.")

        # Ensure leading/trailing slashes are sanitized
        clean_endpoint = endpoint.strip("/")
        url = f"{self.base_url}/{clean_endpoint}"

        client = self._get_client()
        auth = (
            (self._settings.mikrotik_username, self._settings.mikrotik_password)
            if self._custom_client
            else None
        )

        start_time = time.monotonic()
        try:
            response = await client.get(
                url,
                params=params,
                auth=auth,
                timeout=self._settings.mikrotik_timeout,
            )
            duration_ms = (time.monotonic() - start_time) * 1000


            if response.status_code in (401, 403):
                logger.warning(
                    "MikroTik authentication failed",
                    endpoint=clean_endpoint,
                    status_code=response.status_code,
                    host=self._settings.mikrotik_host,
                    duration_ms=round(duration_ms, 2),
                )
                raise MikroTikAuthError(
                    f"Authentication failed on MikroTik router (HTTP {response.status_code})"
                )

            if response.is_error:
                logger.error(
                    "MikroTik API error response",
                    endpoint=clean_endpoint,
                    status_code=response.status_code,
                    body=response.text[:200],
                    duration_ms=round(duration_ms, 2),
                )
                raise MikroTikError(
                    f"MikroTik API error {response.status_code}: {response.text[:200]}"
                )

            logger.debug(
                "MikroTik GET success",
                endpoint=clean_endpoint,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
            return response.json()  # type: ignore[no-any-return]

        except httpx.TimeoutException as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "MikroTik request timed out",
                endpoint=clean_endpoint,
                timeout=self._settings.mikrotik_timeout,
                duration_ms=round(duration_ms, 2),
            )
            raise MikroTikTimeoutError(
                f"Connection to MikroTik router timed out after {self._settings.mikrotik_timeout}s"
            ) from exc

        except httpx.RequestError as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "MikroTik connection failure",
                endpoint=clean_endpoint,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
            )
            raise MikroTikConnectionError(
                f"Unable to connect to MikroTik router at {self._settings.mikrotik_host}: {exc}"
            ) from exc
