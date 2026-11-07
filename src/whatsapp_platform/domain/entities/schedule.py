"""Tugas terjadwal: pengingat dan laporan keuangan otomatis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TaskKind(str, Enum):
    REMINDER = "reminder"
    FINANCE_REPORT = "finance_report"


class Recurrence(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"  # Senin-Jumat
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class ScheduledTask:
    id: str
    owner_jid: str
    # Chat tujuan pengiriman (chat tempat pengingat dibuat; bisa grup).
    chat_jid: str
    kind: TaskKind
    message: str
    recurrence: Recurrence
    # Waktu kirim berikutnya, UTC.
    next_run_at: datetime
    # Tanggal acuan bulanan (1-31) agar "tiap tgl 31" tetap kembali ke 31 setelah bulan pendek.
    anchor_day: int | None
    is_active: bool
    created_at: datetime
    last_run_at: datetime | None = None
    run_count: int = 0
    fail_count: int = 0
    # Nomor urut per pemilik, untuk dirujuk user ("hapus pengingat 3").
    short_id: int = 0
