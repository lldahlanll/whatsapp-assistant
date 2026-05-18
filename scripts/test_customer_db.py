# scripts/test_customer_db.py
"""
Test lookup customer DB.
Run: python scripts/test_customer_db.py 0895378172088
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.db.customer_db import customer_db
from app.services.customer_lookup import customer_lookup

def test_regex():
    """Quick smoke test untuk regex extraction."""
    from app.services.customer_lookup import customer_lookup as cl
    cases = [
        # (input, expected_core_list)
        ("0895378172088", ["895378172088"]),
        ("+6285711112222", ["85711112222"]),
        ("6281234567890", ["81234567890"]),
        ("0812-3456-7890", ["81234567890"]),
        ("(03618479968)", ["3618479968"]),
        ("Pagi pak @71816903155883 nomor (03618479968) tq", ["3618479968"]),
        ("ada 2 nomor: 0812345678901 dan 03612223344", ["812345678901", "3612223344"]),
        ("kode invoice INV2024001", []),  # tidak boleh match
        ("kontak +62 21 5555 1234", ["2155551234"]),  # Jakarta landline
        ("call 1500188", []),  # nomor pendek bukan format ID
    ]
    print("\n🧪 Regex test cases:\n")
    all_pass = True
    for text, expected in cases:
        actual = cl.extract_phone_numbers(text)
        ok = actual == expected
        all_pass = all_pass and ok
        marker = "✓" if ok else "✗"
        print(f"  {marker} {text!r}")
        if not ok:
            print(f"      expected: {expected}")
            print(f"      actual:   {actual}")
    print(f"\n  Result: {'ALL PASS' if all_pass else 'FAIL'}\n")
    return all_pass

async def main(phone_input: str) -> None:
    # Eksekusi test regex terlebih dahulu sebelum lanjut ke DB
    if not test_regex():
        print("⚠️ Regex tests failed — fix dulu sebelum lanjut")
        return

    print(f"\n🔍 Customer DB Lookup Test")
    print(f"   Input: {phone_input!r}\n")

    print("1. Connecting to DB...")
    await customer_db.init()
    print("   ✓ Pool ready\n")

    print("2. Extracting phone numbers...")
    phones = customer_lookup.extract_phone_numbers(phone_input)
    print(f"   ✓ Normalized: {phones}\n")

    if not phones:
        print("   ✗ No valid Indonesian mobile number found")
        await customer_db.close()
        return

    print("3. Querying...")
    for p in phones:
        records = await customer_lookup.lookup_by_phone(p)
        print(f"\n   Phone: {p} → {len(records)} hits")
        for r in records:
            print(
                f"     • Kode={r.kode_kustomer} | "
                f"No_hp={r.no_hp} | "
                f"Sales={r.add_user} | "
                f"Date={r.add_date}"
            )

        print(f"\n   ─── Formatted output ───")
        msg = customer_lookup.format_results(
            p, records, mention_jid="628xxx@s.whatsapp.net"
        )
        print(msg)
        print(f"   ─────────────────────────")

    await customer_db.close()


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else "0895378172088"
    asyncio.run(main(phone))