import os
import os
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# MUST be before any app.* imports
load_dotenv("/home/ephinu/projects/whatsapp-ai-bot/.env")

from loguru import logger
from app.auth.credential_store import credential_store
from app.auth.whitelist import whitelist
from app.config import settings
from app.email.notify_manager import notify_opt_in_manager
from app.email.scheduler import email_scheduler

# ... rest unchanged

C_OK = "\033[92m"
C_FAIL = "\033[91m"
C_BOLD = "\033[1m"
C_END = "\033[0m"

TEST_JID = "test_scheduler_user@s.whatsapp.net"


async def test_opt_in_manager():
    print(f"\n{C_BOLD}[1] NotifyOptInManager{C_END}")

    await notify_opt_in_manager.disable(TEST_JID)  # cleanup

    assert not await notify_opt_in_manager.is_enabled(TEST_JID), "Should be off"
    print(f"  {C_OK}✓{C_END} is_enabled=False after disable")

    await notify_opt_in_manager.enable(TEST_JID)
    assert await notify_opt_in_manager.is_enabled(TEST_JID), "Should be on"
    print(f"  {C_OK}✓{C_END} is_enabled=True after enable")

    all_jids = await notify_opt_in_manager.get_all_opted_in()
    assert TEST_JID in all_jids, f"{TEST_JID} not in {all_jids}"
    print(f"  {C_OK}✓{C_END} get_all_opted_in contains test JID")

    await notify_opt_in_manager.disable(TEST_JID)
    assert not await notify_opt_in_manager.is_enabled(TEST_JID)
    print(f"  {C_OK}✓{C_END} disable removes JID")

    return True


async def test_last_check_persistence():
    print(f"\n{C_BOLD}[2] Last-check timestamp persistence{C_END}")
    from datetime import datetime

    ts_before = datetime.now()
    await email_scheduler._set_last_check(TEST_JID, ts_before)
    ts_after = await email_scheduler._get_last_check(TEST_JID)

    diff = abs((ts_after - ts_before).total_seconds())
    assert diff < 1.0, f"Timestamp drift: {diff}s"
    print(f"  {C_OK}✓{C_END} set/get last_check round-trip (drift={diff:.3f}s)")

    await email_scheduler.reset_last_check(TEST_JID)
    ts_reset = await email_scheduler._get_last_check(TEST_JID)
    assert (datetime.now() - ts_reset).total_seconds() < 5
    print(f"  {C_OK}✓{C_END} reset_last_check sets to ~now")

    return True


async def test_no_credential_auto_optout():
    print(f"\n{C_BOLD}[3] Auto opt-out when no credential{C_END}")

    # Pastikan tidak ada credential untuk TEST_JID
    await credential_store.delete(TEST_JID)
    await notify_opt_in_manager.enable(TEST_JID)
    assert await notify_opt_in_manager.is_enabled(TEST_JID)

    # Jalankan _check_user — harus auto opt-out
    await email_scheduler._check_user(TEST_JID)
    assert not await notify_opt_in_manager.is_enabled(
        TEST_JID
    ), "Should auto opt-out when no credential"
    print(f"  {C_OK}✓{C_END} auto opt-out when credential missing")
    return True


async def main():
    print(f"{C_BOLD}╔══════════════════════════════════════╗{C_END}")
    print(f"{C_BOLD}║  Multi-User Scheduler Tests          ║{C_END}")
    print(f"{C_BOLD}╚══════════════════════════════════════╝{C_END}")

    results = {}
    try:
        results["OptInManager"] = await test_opt_in_manager()
        results["LastCheckPersist"] = await test_last_check_persistence()
        results["NoCredAutoOptOut"] = await test_no_credential_auto_optout()
    finally:
        await notify_opt_in_manager.close()
        await credential_store.close()
        # Cleanup Redis keys
        r = await email_scheduler._get_redis()
        await r.delete(f"email:last_check:{TEST_JID}")
        await email_scheduler.stop()

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{C_BOLD}SUMMARY: {passed}/{total} passed{C_END}")
    for name, ok in results.items():
        marker = f"{C_OK}PASS{C_END}" if ok else f"{C_FAIL}FAIL{C_END}"
        print(f"  [{marker}] {name}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
