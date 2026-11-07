#!/usr/bin/env python3
"""Rekonsiliasi data finance (BACA-SAJA): cek konsistensi saldo & referensi di database SQLite.

Usage:
    python scripts/reconcile_finance.py [path/ke/session.db] [--owner JID]

Yang diperiksa:
  * Saldo rekening vs akumulasi transaksi. Saldo awal rekening tidak punya baris transaksi,
    jadi yang dilaporkan adalah "saldo awal tersirat" = saldo - total mutasi. Nilai selain 0
    wajar jika rekening dibuat dengan saldo awal; yang perlu dicurigai adalah nilai negatif.
  * Saldo minus, referensi yatim (rekening/kategori hilang), kategori & idempotency_key ganda.

Exit code: 0 = tidak ada masalah, 1 = ada temuan (WARNING/ERROR), 2 = DB tidak bisa dibuka.
Skrip membuka DB dengan mode read-only dan tidak mengubah apa pun.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


@dataclass
class Finding:
    level: str  # "ERROR" | "WARNING" | "INFO"
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, message: str) -> None:
        self.findings.append(Finding(level, message))

    @property
    def has_problems(self) -> bool:
        return any(f.level in ("ERROR", "WARNING") for f in self.findings)


def _dec(value: object) -> Decimal:
    return Decimal(str(round(float(value or 0), 2)))


def _tx_deltas(row: sqlite3.Row) -> dict[str, Decimal]:
    """Pengaruh satu baris transaksi ke saldo rekening. Baris reversal membalik arahnya."""
    amount = _dec(row["amount"])
    sign = -1 if row["reversal_of_id"] else 1
    kind = row["transaction_type"]
    if kind == "income":
        return {row["account_id"]: sign * amount}
    if kind == "expense":
        return {row["account_id"]: -sign * amount}
    if kind == "transfer":
        deltas = {row["account_id"]: -sign * amount}
        if row["transfer_to_account_id"]:
            deltas[row["transfer_to_account_id"]] = sign * amount
        return deltas
    return {}


def reconcile(conn: sqlite3.Connection, owner: str | None = None) -> Report:
    conn.row_factory = sqlite3.Row
    report = Report()
    params = {"owner": owner}  # None = semua owner; filter lewat parameter, tanpa merangkai SQL

    account_rows = conn.execute(
        "SELECT * FROM finance_accounts WHERE (:owner IS NULL OR owner_jid = :owner)", params
    )
    accounts = {r["id"]: r for r in account_rows}
    category_rows = conn.execute(
        "SELECT id FROM finance_categories WHERE (:owner IS NULL OR owner_jid = :owner)", params
    )
    categories = {r["id"] for r in category_rows}

    net: dict[str, Decimal] = {}
    tx_count = 0
    for tx in conn.execute("SELECT * FROM finance_transactions WHERE (:owner IS NULL OR owner_jid = :owner)", params):
        tx_count += 1
        # Baris yang dihapus (soft delete) sudah dikembalikan saldonya; abaikan agar tidak terhitung ganda.
        deleted = "deleted_at" in tx.keys() and tx["deleted_at"] is not None
        if deleted:
            continue
        for acc_id in (tx["account_id"], tx["transfer_to_account_id"]):
            if acc_id and acc_id not in accounts:
                label = tx["human_tx_id"] or tx["id"]
                report.add("ERROR", f"Transaksi {label} merujuk rekening yang tidak ada ({acc_id})")
        if tx["category_id"] and tx["category_id"] not in categories:
            report.add("WARNING", f"Transaksi {tx['human_tx_id'] or tx['id']} merujuk kategori yang tidak ada")
        for acc_id, delta in _tx_deltas(tx).items():
            net[acc_id] = net.get(acc_id, Decimal("0")) + delta

    for acc_id, acc in accounts.items():
        balance = _dec(acc["balance"])
        implied_opening = balance - net.get(acc_id, Decimal("0"))
        label = f"{acc['name']} ({acc['owner_jid']})"
        if balance < 0:
            report.add("ERROR", f"Saldo minus pada {label}: {balance}")
        if implied_opening < 0:
            report.add(
                "ERROR",
                f"{label}: saldo {balance} lebih kecil dari total mutasi {net.get(acc_id, 0)} "
                f"(saldo awal tersirat {implied_opening}) — saldo tidak konsisten dengan transaksi",
            )
        elif implied_opening != 0:
            report.add("INFO", f"{label}: saldo awal tersirat {implied_opening} (normal jika dibuat dengan saldo awal)")

    for row in conn.execute(
        "SELECT owner_jid, category_type, name, COUNT(*) c FROM finance_categories "
        "WHERE (:owner IS NULL OR owner_jid = :owner) GROUP BY 1,2,3 HAVING c > 1",
        params,
    ):
        where = f"{row['owner_jid']} / {row['category_type']} / {row['name']}"
        report.add("ERROR", f"Kategori ganda: {where} ({row['c']}x)")

    for row in conn.execute(
        "SELECT owner_jid, idempotency_key, COUNT(*) c FROM finance_transactions "
        "WHERE idempotency_key IS NOT NULL AND (:owner IS NULL OR owner_jid = :owner) GROUP BY 1,2 HAVING c > 1",
        params,
    ):
        report.add("ERROR", f"idempotency_key ganda: {row['owner_jid']} / {row['idempotency_key']} ({row['c']}x)")

    report.add("INFO", f"Diperiksa: {len(accounts)} rekening, {tx_count} transaksi")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rekonsiliasi data finance (baca-saja).")
    parser.add_argument("db", nargs="?", default="storage/session.db", help="Path database SQLite")
    parser.add_argument("--owner", help="Batasi ke satu owner JID")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database tidak ditemukan: {db_path}", file=sys.stderr)
        return 2
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        report = reconcile(conn, args.owner)
    except sqlite3.Error as exc:
        print(f"Tidak bisa membaca database: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            conn.close()
        except NameError:
            pass

    for finding in report.findings:
        print(f"[{finding.level}] {finding.message}")
    print("\nHASIL:", "ADA TEMUAN" if report.has_problems else "OK")
    return 1 if report.has_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
