#!/usr/bin/env python3
"""
Helper script: reset finance data di dalam Docker container.
Di-copy sementara ke container oleh reset_finance.sh — jangan dijalankan langsung.
"""
import sqlite3
import sys

db_path    = sys.argv[1]
target_jid = sys.argv[2] if len(sys.argv) > 2 else ""
dry_run    = (sys.argv[3] if len(sys.argv) > 3 else "false") == "true"

conn = sqlite3.connect(db_path)
tables = ["finance_transactions", "finance_budgets", "finance_accounts", "finance_categories"]

print("\U0001f4ca Data sebelum reset:")
for table in tables:
    if target_jid:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE owner_jid = ?", (target_jid,)
            ).fetchone()[0]
        except Exception:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    else:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"   {table}: {count} baris")

if dry_run:
    print("")
    print("\U0001f50d DRY RUN selesai \u2014 tidak ada yang dihapus.")
    conn.close()
    sys.exit(0)

print("")
print("\U0001f5d1\ufe0f  Menghapus data...")
for table in tables:
    if target_jid:
        try:
            conn.execute(f"DELETE FROM {table} WHERE owner_jid = ?", (target_jid,))
        except Exception:
            conn.execute(f"DELETE FROM {table}")
    else:
        conn.execute(f"DELETE FROM {table}")
    print(f"   \u2705 {table} \u2014 bersih")

conn.commit()
conn.close()
print("")
print("\u2705 Reset selesai! Data finance mulai dari nol bersih.")
print("   Kategori default akan dibuat otomatis saat pertama kali digunakan.")
