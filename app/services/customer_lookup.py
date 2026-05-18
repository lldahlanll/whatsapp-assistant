# app/services/customer_lookup.py
"""Service untuk lookup customer berdasarkan nomor HP."""
import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from app.db.customer_db import customer_db


@dataclass(frozen=True)
class CustomerRecord:
    """Minimal record untuk display di group sales. PII-minimized."""
    kode_kustomer: str
    no_hp: str
    add_user: Optional[str]
    add_date: Optional[str]


class CustomerLookupService:
    """Lookup customer dari DB kantor."""

    SAFE_COLUMNS = ["Kode_kustomer", "No_hp", "Add_user", "AddDate"]

    PHONE_REGEX = re.compile(
        r"(?<![\w\d])"
        r"(?:\+62|62|0)"
        r"[\s\-.]?"
        r"\d(?:[\s\-.]?\d){6,11}"
        r"(?!\d)"
    )

    @staticmethod
    def extract_phone_numbers(text):
        matches = CustomerLookupService.PHONE_REGEX.findall(text)
        normalized = []
        seen = set()
        for raw in matches:
            digits = re.sub(r"\D", "", raw)
            if not digits:
                continue
            if digits.startswith("62"):
                core = digits[2:]
            elif digits.startswith("0"):
                core = digits[1:]
            else:
                core = digits
            if not (8 <= len(core) <= 13):
                continue
            if core[0] not in "2345678":
                continue
            if core not in seen:
                seen.add(core)
                normalized.append(core)
        return normalized

    @staticmethod
    def _format_phone_display(core):
        return f"0{core}"

    @staticmethod
    def _format_date(value):
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        if " " in s:
            s = s.split(" ", 1)[0]
        return s

    @staticmethod
    def _clean_str(value):
        if value is None:
            return None
        s = str(value).strip()
        return s if s else None

    @staticmethod
    def _format_date_id(value):
        """Format tanggal ke gaya Indonesia: '13 Mei 2026'."""
        if not value:
            return None
        s = str(value).strip()
        if not s:
            return None
        if " " in s:
            s = s.split(" ", 1)[0]
        try:
            from datetime import datetime
            dt = datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return s
        bulan = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
        return f"{dt.day} {bulan[dt.month - 1]} {dt.year}"

    async def lookup_by_phone(self, phone_core):
        cols_sql = ", ".join(f"`{c}`" for c in self.SAFE_COLUMNS)
        sql = (
            f"SELECT {cols_sql} "
            f"FROM `kustomer_temp` "
            f"WHERE `No_hp` LIKE %s "
            f"ORDER BY `AddDate` DESC "
            f"LIMIT 5"
        )
        pattern = f"%{phone_core}"
        try:
            rows = await customer_db.fetch_all(sql, (pattern,))
        except Exception as e:
            logger.error(f"[CustomerLookup] DB error for {phone_core}: {e}")
            raise

        records = []
        for row in rows:
            records.append(
                CustomerRecord(
                    kode_kustomer=str(row.get("Kode_kustomer") or "").strip(),
                    no_hp=str(row.get("No_hp") or "").strip(),
                    add_user=CustomerLookupService._clean_str(row.get("Add_user")),
                    add_date=CustomerLookupService._format_date(row.get("AddDate")),
                )
            )
        return records

    @staticmethod
    def format_results(phone, records):
        """
        Format hasil lookup sebagai kalimat untuk sales lapangan.
        Prinsip: lugas, ada konteks tindakan (aman/sudah dipakai),
        bahasa familiar tanpa istilah teknis.
        """
        display = CustomerLookupService._format_phone_display(phone)

        if not records:
            return f"Nomor {display} belum ada di sistem, Silahkan daftarkan ulang."

        r = records[0]
        n_total = len(records)

        date_str = CustomerLookupService._format_date_id(r.add_date)

        # Header kalimat: ada sales atau tidak
        if r.add_user:
            head = f"Nomor {display} sudah dipakai sales {r.add_user}."
        else:
            head = f"Nomor {display} sudah dipakai."

        # Detail tambahan: kode + tanggal
        detail_parts = []
        if r.kode_kustomer:
            detail_parts.append(f"Kode customer: {r.kode_kustomer}")
        if date_str:
            detail_parts.append(f"didaftarkan {date_str}")

        if detail_parts:
            sentence = head + " " + ", ".join(detail_parts) + "."
        else:
            sentence = head

        # Catatan kalau ada multiple record
        if n_total > 1:
            extra = n_total - 1
            if extra == 1:
                sentence += " Catatan: nomor ini punya 1 catatan lama lainnya."
            else:
                sentence += f" Catatan: nomor ini punya {extra} catatan lama lainnya."

        return sentence


customer_lookup = CustomerLookupService()
