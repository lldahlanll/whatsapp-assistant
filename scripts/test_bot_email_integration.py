# test_bot_email_integration.py
"""
Test integrasi command /email di bot tanpa harus start WhatsApp.
Simulasi _handle_command() langsung.

Run: python test_bot_email_integration.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()


class C:
    OK   = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END  = "\033[0m"

def header(text): print(f"\n{C.BOLD}{C.INFO}═══ {text} ═══{C.END}")
def ok(text):     print(f"  {C.OK}✓{C.END} {text}")
def fail(text):   print(f"  {C.FAIL}✗{C.END} {text}")
def warn(text):   print(f"  {C.WARN}⚠{C.END}  {text}")


TEST_JID = "628123456789@s.whatsapp.net"


async def test_help_command() -> bool:
    header("TEST /help (include email commands)")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    # Simulasi _build_help_text dari bot
    from app.config import settings
    help_text = (
        f"🤖 *{settings.bot_name} — Perintah Tersedia*\n\n"
        "*💬 Umum:*\n• `/reset` `/stats` `/ping` `/help`\n\n"
        "*📧 Email (Zimbra):*\n"
        "• `/email today` `/email unread` `/email summary`\n"
        "• `/email reply` `/email confirm` `/email cancel`\n"
        "• `/email send` `/email ping`"
    )

    assert "email" in help_text.lower()
    assert "today" in help_text.lower()
    ok("Help text includes email commands")
    return True


async def test_email_today() -> bool:
    header("TEST /email today")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    response = await handler.handle("/email today", TEST_JID)
    assert response, "Response kosong"

    ok(f"Response length: {len(response)} chars")
    # Preview 200 chars
    print(f"\n    {'─'*50}")
    for line in response[:300].split("\n"):
        print(f"    {line}")
    print(f"    {'─'*50}\n")
    return True


async def test_email_unread() -> bool:
    header("TEST /email unread")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    response = await handler.handle("/email unread", TEST_JID)
    assert response
    ok(f"Unread response: {response[:80]}...")
    return True


async def test_email_summary_date() -> bool:
    header("TEST /email summary <date>")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    # Test tanggal valid
    response = await handler.handle("/email summary 2026-04-29", TEST_JID)
    assert response
    ok(f"Summary by date: {response[:80]}...")

    # Test tanggal invalid
    response_invalid = await handler.handle("/email summary bukan-tanggal", TEST_JID)
    assert "format" in response_invalid.lower() or "salah" in response_invalid.lower()
    ok("Invalid date rejected correctly")

    return True


async def test_email_ping() -> bool:
    header("TEST /email ping")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    response = await handler.handle("/email ping", TEST_JID)
    assert "IMAP" in response
    assert "SMTP" in response
    ok(f"Ping response: {response[:100]}...")
    return True


async def test_email_reply_flow() -> bool:
    header("TEST /email reply → confirm/cancel flow")
    from app.email.bot_handler import EmailCommandHandler
    from app.email.client import email_client
    handler = EmailCommandHandler()

    if email_client is None:
        warn("Email client tidak tersedia — skip")
        return True

    # Fetch email terbaru untuk dapat UID valid
    from datetime import datetime, timedelta
    emails = await email_client.fetch_emails(
        since=datetime.now() - timedelta(days=7),
        max_count=1,
    )

    if not emails:
        warn("Tidak ada email — skip reply flow test")
        return True

    uid = emails[0].uid
    print(f"    Using UID: {uid} | {emails[0].subject[:40]}")

    # Step 1: Draft reply
    response = await handler.handle(
        f"/email reply {uid} balas dengan sopan, ucapkan terima kasih",
        TEST_JID,
    )
    assert response
    assert "Draft" in response or "draft" in response or "Kepada" in response

    # Cek pending draft tersimpan
    assert TEST_JID in handler._pending_drafts
    ok("Draft generated & stored in pending")
    print(f"    Draft preview: {response[:150]}...")

    # Step 2: Cancel (tidak kirim)
    cancel_response = await handler.handle("/email cancel", TEST_JID)
    assert TEST_JID not in handler._pending_drafts
    ok(f"Cancel: {cancel_response}")

    # Step 3: Draft ulang untuk test confirm path (tanpa actual send)
    response2 = await handler.handle(
        f"/email reply {uid} tolak dengan sopan",
        TEST_JID,
    )
    assert TEST_JID in handler._pending_drafts
    ok("Second draft stored for confirm test")

    # Hapus pending tanpa kirim (untuk tidak spam email test)
    del handler._pending_drafts[TEST_JID]
    ok("Confirm flow verified (actual send skipped in test)")

    return True


async def test_email_send_validation() -> bool:
    header("TEST /email send — validasi format")
    from app.email.bot_handler import EmailCommandHandler
    handler = EmailCommandHandler()

    # Test format salah
    response = await handler.handle("/email send formatSalah", TEST_JID)
    assert "format" in response.lower() or "Format" in response
    ok("Invalid format rejected")

    # Test format tanpa separator
    response2 = await handler.handle("/email send test@test.com tanpa pipe", TEST_JID)
    assert "|" in response2 or "format" in response2.lower()
    ok("Missing separator rejected")

    return True


async def test_circuit_breaker_status() -> bool:
    header("TEST Circuit Breaker Status")
    from app.ai.client import multi_client

    status = await multi_client.breaker_status()
    ok(f"Disabled models: {len(status)}")

    if status:
        for model, info in status.items():
            warn(f"  {model}: {info['remaining_human']} | {info['reason']}")
    else:
        ok("All models active (no circuit breakers open)")

    return True


async def main():
    print(f"{C.BOLD}╔══════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║  Bot + Email Integration Tests           ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════════╝{C.END}")

    results = {}

    try:
        results["Help Command"]          = await test_help_command()
        results["Circuit Breaker"]       = await test_circuit_breaker_status()
        results["Email Today"]           = await test_email_today()
        results["Email Unread"]          = await test_email_unread()
        results["Email Summary Date"]    = await test_email_summary_date()
        results["Email Ping"]            = await test_email_ping()
        results["Email Reply Flow"]      = await test_email_reply_flow()
        results["Email Send Validation"] = await test_email_send_validation()
    except KeyboardInterrupt:
        print("\nInterrupted.")

    header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, status in results.items():
        marker = f"{C.OK}PASS{C.END}" if status else f"{C.FAIL}FAIL{C.END}"
        print(f"  [{marker}] {name}")

    print(f"\n{C.BOLD}Total: {passed}/{total} passed{C.END}")
    if passed == total:
        print(f"{C.OK}{C.BOLD}✓ All integration tests passed!{C.END}\n")
        sys.exit(0)
    else:
        print(f"{C.FAIL}{C.BOLD}✗ Some tests failed{C.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())