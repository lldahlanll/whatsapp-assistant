# test_email.py
import asyncio
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv(".env", override=True) if os.path.exists(".env.local") else load_dotenv()

# ── ANSI colors (sama seperti test_aimodel.py) ─────────────────
class C:
    OK   = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END  = "\033[0m"

def header(text: str) -> None:
    print(f"\n{C.BOLD}{C.INFO}═══ {text} ═══{C.END}")

def ok(text: str) -> None:
    print(f"  {C.OK}✓{C.END} {text}")

def fail(text: str) -> None:
    print(f"  {C.FAIL}✗{C.END} {text}")

def warn(text: str) -> None:
    print(f"  {C.WARN}⚠{C.END}  {text}")


# ──────────────────────────────────────────────────────────────
# TEST 1: Config Email
# ──────────────────────────────────────────────────────────────

async def test_email_config() -> bool:
    header("TEST EMAIL CONFIG")

    from app.config import settings

    required = {
        "IMAP Host":     settings.imap_host,
        "SMTP Host":     settings.smtp_host,
        "Email User":    settings.email_username,
        "Email Pass":    settings.email_password,
    }

    optional = {
        "Sender Name":   settings.email_sender_name,
        "Notify JID":    settings.email_notify_jid,
        "Poll Interval": f"{settings.email_poll_interval_seconds}s",
    }

    all_ok = True
    for name, value in required.items():
        if value:
            ok(f"{name}: {'*' * 4 + value[-4:] if 'pass' in name.lower() else value}")
        else:
            fail(f"{name}: NOT SET")
            all_ok = False

    print()
    for name, value in optional.items():
        status = "○" if value else "–"
        print(f"    {status} {name}: {value or '(not set)'}")

    if not all_ok:
        warn("Set email config di .env sebelum test lanjut")

    return all_ok


# ──────────────────────────────────────────────────────────────
# TEST 2: IMAP + SMTP Connection
# ──────────────────────────────────────────────────────────────

async def test_connection() -> bool:
    header("TEST CONNECTION (IMAP + SMTP)")

    from app.email.client import email_client

    if email_client is None:
        fail("Email client tidak terinisialisasi — cek config")
        return False

    result = await email_client.test_connection()

    imap_ok = result.get("imap", False)
    smtp_ok = result.get("smtp", False)

    if imap_ok:
        ok("IMAP connection: OK")
    else:
        fail("IMAP connection: FAILED")

    if smtp_ok:
        ok("SMTP connection: OK")
    else:
        fail("SMTP connection: FAILED")

    return imap_ok and smtp_ok


# ──────────────────────────────────────────────────────────────
# TEST 3: Fetch Emails
# ──────────────────────────────────────────────────────────────

async def test_fetch_emails() -> bool:
    header("TEST FETCH EMAILS")

    from app.email.client import email_client

    if email_client is None:
        warn("Email client tidak tersedia — skip")
        return True

    # Fetch email 7 hari terakhir
    since = datetime.now() - timedelta(days=7)

    print(f"    Fetching emails since {since.strftime('%Y-%m-%d')}...")
    emails = await email_client.fetch_emails(since=since, max_count=5)

    if emails is None:
        fail("Fetch returned None")
        return False

    ok(f"Fetched {len(emails)} emails")

    if emails:
        e = emails[0]
        ok(f"Sample email:")
        print(f"      UID     : {e.uid}")
        print(f"      Subject : {e.subject[:50]}")
        print(f"      From    : {e.sender_email}")
        print(f"      Date    : {e.received_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"      Read    : {e.is_read}")
        print(f"      Body    : {e.body[:80]}...")
        if e.attachments:
            print(f"      Attach  : {e.attachments}")

        # Validasi struktur
        assert e.uid, "UID kosong"
        assert isinstance(e.subject, str), "Subject bukan string"
        assert isinstance(e.body, str), "Body bukan string"
        assert isinstance(e.received_at, datetime), "Date bukan datetime"
        ok("EmailMessage structure valid")

    return True


# ──────────────────────────────────────────────────────────────
# TEST 4: Unread Count
# ──────────────────────────────────────────────────────────────

async def test_unread_count() -> bool:
    header("TEST UNREAD COUNT")

    from app.email.client import email_client

    if email_client is None:
        warn("Skip — email client tidak tersedia")
        return True

    count = await email_client.get_unread_count()
    if count >= 0:
        ok(f"Unread emails in INBOX: {count}")
        return True
    else:
        fail("get_unread_count returned error")
        return False


# ──────────────────────────────────────────────────────────────
# TEST 5: AI Summarize
# ──────────────────────────────────────────────────────────────

async def test_ai_summarize() -> bool:
    header("TEST AI SUMMARIZE")

    from app.email.agent import email_agent

    since = datetime.now() - timedelta(days=7)
    print("    Running fetch + AI summarize (7 hari terakhir)...")

    summary = await email_agent.fetch_and_summarize(
        since=since,
        date_label="7 hari terakhir",
        max_count=5,
    )

    if not summary:
        fail("Summary kosong")
        return False

    ok(f"Summary length: {len(summary)} chars")
    print(f"\n    {'─' * 50}")
    # Tampilkan 500 char pertama
    preview = summary[:500] + ("..." if len(summary) > 500 else "")
    for line in preview.split("\n"):
        print(f"    {line}")
    print(f"    {'─' * 50}\n")

    return True


# ──────────────────────────────────────────────────────────────
# TEST 6: Draft Reply (tanpa kirim)
# ──────────────────────────────────────────────────────────────

async def test_draft_reply() -> bool:
    header("TEST DRAFT REPLY (no send)")

    from app.email.client import email_client
    from app.email.agent import email_agent

    if email_client is None:
        warn("Skip — email client tidak tersedia")
        return True

    # Ambil email terbaru untuk di-test
    since = datetime.now() - timedelta(days=7)
    emails = await email_client.fetch_emails(since=since, max_count=1)

    if not emails:
        warn("Tidak ada email untuk di-test reply — skip")
        return True

    target = emails[0]
    print(f"    Target email: UID={target.uid} | {target.subject[:40]}")

    draft, original = await email_agent.draft_reply(
        uid=target.uid,
        instruction="balas dengan sopan, ucapkan terima kasih sudah menghubungi",
    )

    if original is None:
        fail(f"Draft reply gagal: {draft}")
        return False

    ok(f"Draft generated ({len(draft)} chars)")
    print(f"\n    {'─' * 40}")
    preview = draft[:300] + ("..." if len(draft) > 300 else "")
    for line in preview.split("\n"):
        print(f"    {line}")
    print(f"    {'─' * 40}\n")

    # TIDAK mengirim — hanya test generation
    ok("Draft reply test PASSED (email tidak dikirim)")
    return True


# ──────────────────────────────────────────────────────────────
# TEST 7: Command Handler Routing
# ──────────────────────────────────────────────────────────────

async def test_command_handler() -> bool:
    header("TEST COMMAND HANDLER ROUTING")

    from app.email.bot_handler import EmailCommandHandler

    handler = EmailCommandHandler()
    test_jid = "628123456789@s.whatsapp.net"

    # Test help command
    response = await handler.handle("/email help", test_jid)
    assert "today" in response.lower(), "Help harus mention 'today'"
    assert "reply" in response.lower(), "Help harus mention 'reply'"
    ok("Help command: OK")

    # Test ping command
    response = await handler.handle("/email ping", test_jid)
    ok(f"Ping command: {response[:60]}...")

    # Test invalid date format
    response = await handler.handle("/email summary invalid-date", test_jid)
    assert "format" in response.lower() or "salah" in response.lower()
    ok("Invalid date validation: OK")

    # Test cancel tanpa pending
    response = await handler.handle("/email cancel", test_jid)
    assert "tidak ada" in response.lower()
    ok("Cancel without pending: OK")

    # Test confirm tanpa pending
    response = await handler.handle("/email confirm", test_jid)
    assert "tidak ada" in response.lower()
    ok("Confirm without pending: OK")

    return True


# ──────────────────────────────────────────────────────────────
# Main runner
# ──────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"{C.BOLD}╔══════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║   Zimbra Email Integration Tests     ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════╝{C.END}")

    results: dict[str, bool] = {}

    try:
        results["Email Config"]      = await test_email_config()
        results["Connection"]        = await test_connection()
        results["Fetch Emails"]      = await test_fetch_emails()
        results["Unread Count"]      = await test_unread_count()
        results["AI Summarize"]      = await test_ai_summarize()
        results["Draft Reply"]       = await test_draft_reply()
        results["Command Handler"]   = await test_command_handler()
    except KeyboardInterrupt:
        print("\nTest interrupted.")

    # Summary
    header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, status in results.items():
        marker = f"{C.OK}PASS{C.END}" if status else f"{C.FAIL}FAIL{C.END}"
        print(f"  [{marker}] {name}")

    print(f"\n{C.BOLD}Total: {passed}/{total} passed{C.END}")

    if passed == total:
        print(f"{C.OK}{C.BOLD}✓ All email tests passed!{C.END}\n")
        sys.exit(0)
    else:
        print(f"{C.FAIL}{C.BOLD}✗ Some tests failed{C.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())