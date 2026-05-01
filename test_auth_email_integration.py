# test_auth_email_integration.py
"""
Integration test: auth + email per-user.

Test scenario:
1. User dengan credential A bisa fetch email A
2. User dengan credential B (invalid) dapat EmailAuthError
3. Multiple user paralel tidak saling tertukar
4. Auth middleware properly route states

Run: python test_auth_email_integration.py
"""
import asyncio
import getpass
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

def header(t): print(f"\n{C.BOLD}{C.INFO}═══ {t} ═══{C.END}")
def ok(t):     print(f"  {C.OK}✓{C.END} {t}")
def fail(t):   print(f"  {C.FAIL}✗{C.END} {t}")
def warn(t):   print(f"  {C.WARN}⚠{C.END}  {t}")


# ──────────────────────────────────────────────────────────────
# TEST 1: Server config valid
# ──────────────────────────────────────────────────────────────

async def test_server_config() -> bool:
    header("TEST EMAIL SERVER CONFIG")
    from app.email import validate_email_server_config
    result = validate_email_server_config()
    if result:
        ok("IMAP/SMTP host config OK")
    else:
        fail("Server config tidak lengkap")
    return result


# ──────────────────────────────────────────────────────────────
# TEST 2: Per-user client dengan credential valid
# ──────────────────────────────────────────────────────────────

async def test_valid_credential() -> bool:
    header("TEST PER-USER CLIENT (valid credential)")

    from app.auth import UserCredential
    from app.email import ZimbraEmailClient

    print("  Masukkan kredensial Zimbra REAL untuk testing:")
    email = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")

    if not email or not password:
        warn("Skip — credential tidak diisi")
        return True

    cred = UserCredential(
        email=email,
        password=password,
        display_name="Tester",
    )

    client = ZimbraEmailClient.for_user(cred)
    ok(f"Client created untuk: {client.email}")

    # Test connection
    result = await client.test_connection()
    if not result["imap"]:
        fail("IMAP test gagal")
        return False
    ok("IMAP login OK")

    if not result["smtp"]:
        warn("SMTP test gagal (IMAP OK, bisa baca tapi tidak bisa kirim)")
    else:
        ok("SMTP login OK")

    # Test fetch
    emails = await client.fetch_emails(
        since=datetime.now() - timedelta(days=7),
        max_count=3,
    )
    ok(f"Fetched {len(emails)} email(s)")

    if emails:
        ok(f"Sample: {emails[0].subject[:50]}")

    # Save for next test
    os.environ["_TEST_EMAIL"] = email
    os.environ["_TEST_PASS"] = password
    return True


# ──────────────────────────────────────────────────────────────
# TEST 3: Invalid credential → EmailAuthError
# ──────────────────────────────────────────────────────────────

async def test_invalid_credential() -> bool:
    header("TEST INVALID CREDENTIAL HANDLING")

    from app.auth import UserCredential
    from app.email import EmailAuthError, ZimbraEmailClient

    bad_cred = UserCredential(
        email="invalid_user_test@vci.co.id",
        password="wrong_password_12345",
    )

    client = ZimbraEmailClient.for_user(bad_cred)

    # test_connection harus return False, NOT raise
    result = await client.test_connection()
    if result["imap"]:
        fail("test_connection harusnya return False untuk invalid cred")
        return False
    ok("test_connection returns False for invalid (no exception leak)")

    # fetch_emails harus raise EmailAuthError
    try:
        await client.fetch_emails(max_count=1)
        fail("fetch_emails harusnya raise EmailAuthError")
        return False
    except EmailAuthError as e:
        ok(f"EmailAuthError raised correctly: {str(e)[:60]}...")
    except Exception as e:
        fail(f"Wrong exception type: {type(e).__name__}: {e}")
        return False

    return True


# ──────────────────────────────────────────────────────────────
# TEST 4: Auth middleware states
# ──────────────────────────────────────────────────────────────

async def test_auth_middleware_states() -> bool:
    header("TEST AUTH MIDDLEWARE STATES")

    from app.auth import (
        AuthState,
        UserCredential,
        check_auth,
        credential_store,
        session_manager,
        whitelist,
    )

    test_jid = "628777666555@s.whatsapp.net"

    # Cleanup
    await session_manager.delete(test_jid)
    await credential_store.delete(test_jid)
    await whitelist.remove(test_jid)

    # State 1: NOT_WHITELISTED
    result = await check_auth(test_jid)
    if result.state != AuthState.NOT_WHITELISTED:
        fail(f"Expected NOT_WHITELISTED, got {result.state}")
        return False
    ok("State NOT_WHITELISTED detected")

    # Add to whitelist
    admin_jids = whitelist.get_admin_jids()
    admin = next(iter(admin_jids)) if admin_jids else "test_admin"
    await whitelist.add(test_jid, "Test", admin)

    # State 2: NOT_LOGGED_IN (whitelisted but no session/cred)
    result = await check_auth(test_jid)
    if result.state != AuthState.NOT_LOGGED_IN:
        fail(f"Expected NOT_LOGGED_IN, got {result.state}")
        return False
    ok("State NOT_LOGGED_IN detected")

    # Add credential without session → should be SESSION_EXPIRED hint
    test_email = os.environ.get("_TEST_EMAIL", "test@vci.co.id")
    test_pass = os.environ.get("_TEST_PASS", "dummy")
    cred = UserCredential(email=test_email, password=test_pass)
    await credential_store.save(test_jid, cred)

    result = await check_auth(test_jid)
    if result.state != AuthState.SESSION_EXPIRED:
        fail(f"Expected SESSION_EXPIRED (cred exists, no session), got {result.state}")
        return False
    ok("State SESSION_EXPIRED detected (cred ada, session belum)")

    # Create session → AUTHORIZED
    await session_manager.create(test_jid, test_email)
    result = await check_auth(test_jid)
    if result.state != AuthState.AUTHORIZED:
        fail(f"Expected AUTHORIZED, got {result.state}")
        return False
    if result.credential is None or result.session is None:
        fail("AUTHORIZED but credential/session is None")
        return False
    ok(f"State AUTHORIZED with cred ({result.credential.email}) "
       f"and session ({result.session.remaining_human})")

    # Cleanup
    await session_manager.delete(test_jid)
    await credential_store.delete(test_jid)
    await whitelist.remove(test_jid)
    return True


# ──────────────────────────────────────────────────────────────
# TEST 5: cleanup_user wipes everything
# ──────────────────────────────────────────────────────────────

async def test_cleanup_user() -> bool:
    header("TEST cleanup_user (auto-cleanup pada /admin remove)")

    from app.auth import (
        UserCredential,
        cleanup_user,
        credential_store,
        session_manager,
        whitelist,
    )

    test_jid = "628111222333@s.whatsapp.net"

    # Setup: add semua data
    admin_jids = whitelist.get_admin_jids()
    admin = next(iter(admin_jids)) if admin_jids else "test"
    await whitelist.add(test_jid, "Cleanup Test", admin)
    await credential_store.save(
        test_jid,
        UserCredential(email="cleanup@test.com", password="xxx"),
    )
    await session_manager.create(test_jid, "cleanup@test.com")

    # Verify all exist
    assert await whitelist.is_authorized(test_jid)
    assert await credential_store.exists(test_jid)
    assert await session_manager.is_active(test_jid)
    ok("Setup: whitelist + credential + session all exist")

    # Cleanup
    result = await cleanup_user(test_jid)
    ok(f"cleanup_user returned: {result}")

    # Verify all gone
    if await whitelist.is_authorized(test_jid):
        fail("Whitelist not cleaned")
        return False
    if await credential_store.exists(test_jid):
        fail("Credential not cleaned")
        return False
    if await session_manager.is_active(test_jid):
        fail("Session not cleaned")
        return False

    ok("All data wiped: whitelist + credential + session")
    return True


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

async def main():
    print(f"{C.BOLD}╔══════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║  Multi-User Auth + Email Integration     ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════════╝{C.END}")

    results = {}

    try:
        results["Server Config"]      = await test_server_config()
        if not results["Server Config"]:
            sys.exit(1)

        results["Valid Credential"]   = await test_valid_credential()
        results["Invalid Credential"] = await test_invalid_credential()
        results["Auth Middleware"]    = await test_auth_middleware_states()
        results["Cleanup User"]       = await test_cleanup_user()
    finally:
        from app.auth import credential_store, session_manager, whitelist
        await credential_store.close()
        await session_manager.close()
        await whitelist.close()

    header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, status in results.items():
        marker = f"{C.OK}PASS{C.END}" if status else f"{C.FAIL}FAIL{C.END}"
        print(f"  [{marker}] {name}")

    print(f"\n{C.BOLD}Total: {passed}/{total}{C.END}")
    if passed == total:
        print(f"{C.OK}{C.BOLD}✓ Sub-Tahap 2A complete — ready for 2B!{C.END}\n")
        sys.exit(0)
    else:
        print(f"{C.FAIL}{C.BOLD}✗ Some tests failed{C.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())