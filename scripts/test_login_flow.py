# scripts/test_login_flow.py
"""
Simulasi flow login user real (tanpa WhatsApp).

Flow yang ditest:
1. User belum di-whitelist → reject
2. Admin tambahkan ke whitelist
3. User login dengan kredensial Zimbra real
4. Verifikasi kredensial via IMAP test
5. Bot bisa fetch email pakai kredensial yang tersimpan
6. Logout

Run dari root project: python scripts/test_login_flow.py
"""
import asyncio
import getpass
import os
import sys
from pathlib import Path

# Add parent dir ke sys.path agar bisa import app.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def step(num, text):
    print(f"\n{C.BOLD}{C.INFO}[{num}] {text}{C.END}")
    print("─" * 60)


def ok(text):  print(f"  {C.OK}✓{C.END} {text}")
def fail(text): print(f"  {C.FAIL}✗{C.END} {text}")
def warn(text): print(f"  {C.WARN}⚠{C.END}  {text}")


async def main():
    print(f"{C.BOLD}╔══════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║  Login Flow Simulation                   ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════════╝{C.END}")

    from app.auth import (
        credential_store,
        session_manager,
        whitelist,
        UserCredential,
    )

    # Test JID untuk simulasi user
    test_jid = "628999000111@s.whatsapp.net"
    test_name = "Tester User"

    # ── Step 1: Cek user belum di-whitelist ───────────────────
    step(1, "User mencoba akses tanpa di-whitelist")

    is_authorized = await whitelist.is_authorized(test_jid)
    if is_authorized:
        warn(f"User {test_jid} sudah authorized (cleanup dari run sebelumnya?)")
        await whitelist.remove(test_jid)
        is_authorized = await whitelist.is_authorized(test_jid)

    if is_authorized:
        fail("User TIDAK seharusnya authorized")
        sys.exit(1)
    ok(f"User {test_jid} → REJECTED (belum di-whitelist)")

    # ── Step 2: Admin tambahkan user ──────────────────────────
    step(2, "Admin menambahkan user ke whitelist")

    admin_jids = whitelist.get_admin_jids()
    if not admin_jids:
        fail("Tidak ada admin di .env (ADMIN_JIDS kosong)")
        sys.exit(1)

    admin_jid = next(iter(admin_jids))
    ok(f"Admin JID: {admin_jid}")

    added = await whitelist.add(test_jid, test_name, admin_jid)
    if not added:
        fail("Gagal tambah user ke whitelist")
        sys.exit(1)
    ok(f"User '{test_name}' ({test_jid}) ditambahkan")

    # Verifikasi
    is_authorized_now = await whitelist.is_authorized(test_jid)
    if not is_authorized_now:
        fail("User belum authorized setelah ditambahkan")
        sys.exit(1)
    ok("User sekarang authorized")

    # ── Step 3: User login ────────────────────────────────────
    step(3, "User login dengan kredensial Zimbra")

    print(f"\n  {C.BOLD}Masukkan kredensial Zimbra REAL untuk testing:{C.END}")
    print(f"  {C.WARN}(kredensial ini akan disimpan terenkripsi){C.END}\n")

    email = input("  Email Zimbra: ").strip()
    if not email or "@" not in email:
        fail("Email tidak valid, abort")
        await whitelist.remove(test_jid)
        sys.exit(1)

    password = getpass.getpass("  Password   : ")
    if not password:
        fail("Password kosong, abort")
        await whitelist.remove(test_jid)
        sys.exit(1)

    display_name = input("  Display name (kosong = pakai email): ").strip() or email

    # ── Step 4: Verifikasi kredensial via IMAP test ───────────
    step(4, "Testing kredensial via IMAP login")

    # Test login langsung tanpa simpan dulu
    from app.email.client import ZimbraEmailClient

    # Override settings sementara untuk test
    original_user = os.environ.get("EMAIL_USERNAME", "")
    original_pass = os.environ.get("EMAIL_PASSWORD", "")
    os.environ["EMAIL_USERNAME"] = email
    os.environ["EMAIL_PASSWORD"] = password

    # Reload settings (singleton invalidation)
    from app.config import get_settings
    get_settings.cache_clear()
    from app.config import settings as fresh_settings

    test_client = ZimbraEmailClient()
    test_result = await test_client.test_connection()

    # Restore env
    if original_user:
        os.environ["EMAIL_USERNAME"] = original_user
    else:
        os.environ.pop("EMAIL_USERNAME", None)
    if original_pass:
        os.environ["EMAIL_PASSWORD"] = original_pass
    else:
        os.environ.pop("EMAIL_PASSWORD", None)
    get_settings.cache_clear()

    if not test_result.get("imap"):
        fail("IMAP login GAGAL — kredensial salah atau server unreachable")
        await whitelist.remove(test_jid)
        sys.exit(1)
    ok("IMAP login berhasil")

    if not test_result.get("smtp"):
        warn("SMTP login gagal (tapi IMAP OK — bisa baca email tapi tidak bisa kirim)")
    else:
        ok("SMTP login berhasil")

    # ── Step 5: Save kredensial terenkripsi ───────────────────
    step(5, "Menyimpan kredensial terenkripsi")

    cred = UserCredential(
        email=email,
        password=password,
        display_name=display_name,
    )
    saved = await credential_store.save(test_jid, cred)
    if not saved:
        fail("Gagal simpan credential")
        sys.exit(1)
    ok("Credential tersimpan terenkripsi")

    # ── Step 6: Buat session ──────────────────────────────────
    step(6, "Membuat session 8 jam")

    session = await session_manager.create(test_jid, email)
    ok(f"Session dibuat, expire dalam {session.remaining_human}")

    # ── Step 7: Verifikasi end-to-end ─────────────────────────
    step(7, "End-to-end verification")

    # Cek bisa retrieve credential
    retrieved = await credential_store.get(test_jid)
    if retrieved is None or retrieved.email != email:
        fail("Credential tidak bisa di-retrieve")
        sys.exit(1)
    ok(f"Credential retrieved: {retrieved.email}")

    # Cek session aktif
    if not await session_manager.is_active(test_jid):
        fail("Session tidak aktif")
        sys.exit(1)
    ok("Session aktif")

    # Test fetch email pakai kredensial tersimpan
    print(f"\n  Testing fetch email dengan kredensial tersimpan...")
    os.environ["EMAIL_USERNAME"] = retrieved.email
    os.environ["EMAIL_PASSWORD"] = retrieved.password
    get_settings.cache_clear()

    fresh_client = ZimbraEmailClient()
    unread = await fresh_client.get_unread_count()

    # Restore
    if original_user:
        os.environ["EMAIL_USERNAME"] = original_user
    else:
        os.environ.pop("EMAIL_USERNAME", None)
    if original_pass:
        os.environ["EMAIL_PASSWORD"] = original_pass
    else:
        os.environ.pop("EMAIL_PASSWORD", None)
    get_settings.cache_clear()

    if unread < 0:
        fail("Fetch email gagal")
    else:
        ok(f"Bot bisa baca email user: {unread} unread emails")

    # ── Step 8: Cleanup ───────────────────────────────────────
    step(8, "Cleanup test data")

    await session_manager.delete(test_jid)
    await credential_store.delete(test_jid)
    await whitelist.remove(test_jid)
    ok("Semua test data dibersihkan")

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{C.BOLD}{'═' * 60}{C.END}")
    print(f"{C.OK}{C.BOLD}✓ Login flow BERHASIL — multi-user system siap dipakai!{C.END}")
    print(f"{C.BOLD}{'═' * 60}{C.END}\n")

    # Cleanup connections
    await credential_store.close()
    await session_manager.close()
    await whitelist.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDibatalkan oleh user.")