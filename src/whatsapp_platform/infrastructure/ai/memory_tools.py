"""Definisi tool LLM untuk memori persisten pengguna (memory_save / memory_forget).

Eksekutornya ada di ``memory_executor`` agar modul ini bebas dari import layer features
(context_policy mengimpor modul ini).
"""

from __future__ import annotations

import re

from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition, ToolParameter

MEMORY_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="memory_save",
        description=(
            "Simpan fakta jangka panjang tentang pengguna yang ia minta untuk diingat, "
            "misal nama panggilan, preferensi, pekerjaan, rekening utama, atau kebiasaan. "
            "Tulis sebagai satu kalimat singkat orang ketiga, contoh: 'Ingin dipanggil Mas Dahlan'. "
            "JANGAN dipakai untuk pengingat berwaktu, jadwal, atau mencatat transaksi keuangan."
        ),
        parameters=[
            ToolParameter(
                name="fact",
                type="string",
                description="Fakta singkat (maks 200 karakter) yang akan diingat.",
                required=True,
            ),
        ],
    ),
    ToolDefinition(
        name="memory_forget",
        description=(
            "Hapus fakta yang sebelumnya disimpan ketika pengguna meminta untuk dilupakan."
        ),
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Potongan teks fakta yang ingin dihapus, contoh: 'dipanggil'.",
                required=True,
            ),
        ],
    ),
]

# Kalimat yang menandakan pengguna ingin bot mengingat/melupakan sesuatu.
# "ingatkan"/"ingetin" sengaja tidak masuk: itu pengingat berwaktu, bukan memori.
MEMORY_INTENT_PATTERN = re.compile(
    r"(?i)\b("
    r"(tolong |coba )?ingat(lah)?( ya| bahwa| kalau| kalo|,)|inget( ya| bahwa| kalau| kalo|,)|"
    r"simpan (info|informasi|fakta)|"
    r"panggil (aku|saya|gue|gw)|nama (aku|saya|ku|gue)|namaku|"
    r"(aku|saya|gue) lebih suka|"
    r"lupakan|lupain|hapus (dari )?(ingatan|memori)|jangan ingat"
    r")"
)


def wants_memory_tools(text: str) -> bool:
    return bool(text and MEMORY_INTENT_PATTERN.search(text))
