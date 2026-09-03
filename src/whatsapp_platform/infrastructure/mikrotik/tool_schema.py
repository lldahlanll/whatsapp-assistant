"""Tool schemas and definitions for MikroTik RouterOS LLM Tool Calling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """Parameter definition for an LLM tool."""

    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = False
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    """Provider-agnostic tool definition."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI / Groq tool schema format."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_gemini_schema(self) -> dict[str, Any]:
        """Convert to Gemini function_declaration format."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        type_map = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
        }

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": type_map.get(param.type, "STRING"),
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        schema: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
            },
        }
        if required:
            schema["parameters"]["required"] = required
        return schema


MIKROTIK_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="mikrotik_get_health",
        description=(
            "Mendapatkan status kesehatan dan kondisi router MikroTik secara menyeluruh. "
            "Mengembalikan metrik CPU load, temperatur, voltase, penggunaan RAM, storage/HDD, uptime, "
            "board name, RouterOS version, dan overall health score (0-100)."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="mikrotik_get_traffic",
        description=(
            "Mendapatkan statistik traffic dan utilisasi bandwidth real-time pada interface router "
            "(seperti WAN, ether1, bridge, pppoe). Mengembalikan rx/tx rate dalam bps, status link, "
            "dan estimasi kecepatan bandwidth."
        ),
        parameters=[
            ToolParameter(
                name="interface_name",
                type="string",
                description=(
                    "Nama interface spesifik (contoh: 'ether1', 'ether1-WAN', 'bridge', 'wlan1')."
                    " Jika kosong, mengembalikan traffic semua interface."
                ),
                required=False,
            )
        ],
    ),
    ToolDefinition(
        name="mikrotik_get_dhcp_leases",
        description=(
            "Mendapatkan daftar perangkat client yang terhubung ke jaringan via DHCP server MikroTik. "
            "Mengembalikan IP address, MAC address, hostname perangkat, dan status active/bound."
        ),
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description=(
                    "Kata kunci pencarian opsional (misal hostname perangkat 'iPhone',"
                    " alamat IP '192.168.1.50', atau MAC address). Kosongkan untuk melihat semua client."
                ),
                required=False,
            )
        ],
    ),
    ToolDefinition(
        name="mikrotik_audit_security",
        description=(
            "Melakukan audit keamanan router MikroTik untuk mendeteksi celah dan risiko keamanan. "
            "Memeriksa service berbahaya yang terbuka (Telnet, FTP, WWW tanpa SSL, WinBox non-standar), "
            "dan konfigurasi DNS remote requests."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="mikrotik_get_firewall",
        description=(
            "Mendapatkan ringkasan konfigurasi Firewall Filter Rules dan NAT (Network Address Translation) "
            "pada router MikroTik."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="mikrotik_get_routes",
        description=(
            "Mendapatkan tabel routing IP router MikroTik, status gateway default internet,"
            " dan status keaktifan jalur route."
        ),
        parameters=[],
    ),
    ToolDefinition(
        name="mikrotik_get_logs",
        description=(
            "Mendapatkan log aktivitas sistem terbaru dari router MikroTik untuk troubleshooting. "
            "Bisa melihat event error, login gagal, interface link up/down, firewall drop, dll."
        ),
        parameters=[
            ToolParameter(
                name="topic",
                type="string",
                description=(
                    "Filter topik log (contoh: 'system', 'firewall', 'critical', 'warning', 'dhcp', 'error')."
                    " Kosongkan untuk log umum."
                ),
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Jumlah baris log terbaru yang diambil (default 15, maksimal 30).",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="mikrotik_get_connections",
        description=(
            "Mendapatkan ringkasan active connection tracking table pada router MikroTik"
            " (jumlah koneksi TCP, UDP, ICMP)."
        ),
        parameters=[],
    ),
]
