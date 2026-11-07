"""Definisi tool LLM untuk pengingat & laporan terjadwal (reminder_*).

Eksekutornya ada di ``reminder_executor`` agar modul ini bebas dari import layer features
(context_policy mengimpor modul ini).
"""

from __future__ import annotations

import re

from whatsapp_platform.infrastructure.mikrotik.tool_schema import ToolDefinition, ToolParameter

REMINDER_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="reminder_create",
        description=(
            "Buat pengingat atau laporan terjadwal yang nanti DIKIRIM BOT ke chat ini pada waktunya. "
            "Contoh: 'ingetin minum obat tiap hari jam 8' -> message='Minum obat', recurrence='daily', "
            "time='08:00'. '30 menit lagi ingetin angkat jemuran' -> delay_minutes=30. "
            "'ingatkan bayar listrik tiap tanggal 5' -> recurrence='monthly', day_of_month=5. "
            "'kirim laporan keuangan tiap senin jam 7' -> kind='finance_report', recurrence='weekly', "
            "weekday='senin', time='07:00'. Untuk waktu relatif ('X menit/jam lagi') WAJIB pakai "
            "delay_minutes, jangan menebak jam sekarang. Jangan mencatat transaksi keuangan dengan tool ini."
        ),
        parameters=[
            ToolParameter(
                name="message",
                type="string",
                description="Isi pengingat singkat, mis. 'Minum obat'. Boleh kosong untuk finance_report.",
                required=False,
            ),
            ToolParameter(
                name="kind",
                type="string",
                description="'reminder' (default) atau 'finance_report' (ringkasan keuangan otomatis).",
                required=False,
                enum=["reminder", "finance_report"],
            ),
            ToolParameter(
                name="recurrence",
                type="string",
                description="Pengulangan: once (default), daily, weekdays (Senin-Jumat), weekly, monthly.",
                required=False,
                enum=["once", "daily", "weekdays", "weekly", "monthly"],
            ),
            ToolParameter(
                name="delay_minutes",
                type="integer",
                description="Untuk waktu relatif: kirim N menit dari sekarang (1 jam = 60).",
                required=False,
            ),
            ToolParameter(
                name="time",
                type="string",
                description="Jam lokal WIB format HH:MM 24 jam, mis. '08:00', '15:30'.",
                required=False,
            ),
            ToolParameter(
                name="date",
                type="string",
                description="Tanggal spesifik YYYY-MM-DD untuk pengingat sekali jalan (pakai bersama 'time').",
                required=False,
            ),
            ToolParameter(
                name="weekday",
                type="string",
                description="Nama hari untuk jadwal mingguan: senin, selasa, rabu, kamis, jumat, sabtu, minggu.",
                required=False,
            ),
            ToolParameter(
                name="day_of_month",
                type="integer",
                description="Tanggal 1-31 untuk jadwal bulanan.",
                required=False,
            ),
        ],
    ),
    ToolDefinition(
        name="reminder_list",
        description="Tampilkan daftar pengingat/jadwal aktif milik pengguna beserta nomornya.",
        parameters=[],
    ),
    ToolDefinition(
        name="reminder_cancel",
        description=(
            "Hapus/hentikan pengingat berdasarkan nomornya. Jika nomor tidak diketahui, panggil "
            "reminder_list dulu dan tanyakan pengguna mana yang dimaksud."
        ),
        parameters=[
            ToolParameter(
                name="number",
                type="integer",
                description="Nomor pengingat dari reminder_list.",
                required=True,
            ),
        ],
    ),
]

# Kata kerja pengingat berwaktu. Sengaja spesifik: "tiap bulan" saja (mis. budget bulanan) bukan pengingat.
REMINDER_INTENT_PATTERN = re.compile(
    r"(?i)\b("
    r"ingatkan|ingetin|ingatin|ingetkan|ingat\s?in|"
    r"pengingat|reminder|remind|alarm|"
    r"jadwalkan|jadwalin|"
    r"(kirim|kirimin|kirimkan)\s+(aku\s+|saya\s+)?(laporan|rekap|ringkasan)\b[^.?!]*\b(tiap|setiap)"
    r")"
)


def wants_reminder_tools(text: str) -> bool:
    return bool(text and REMINDER_INTENT_PATTERN.search(text))
