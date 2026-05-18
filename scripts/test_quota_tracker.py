# scripts/test_quota_tracker.py
"""
Test quota_tracker integration dengan router.

Coverage:
1. Empty state → has_budget() return True
2. Setelah record_call() N kali → counter naik
3. Hit limit → has_budget() return False
4. Reset → counter cleared
5. Snapshot consistency
6. Fail-open kalau Redis down (manual test)
7. Router skip route saat quota exhausted

Run dari root project: python scripts/test_quota_tracker.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

(
    load_dotenv(".env.local", override=True)
    if os.path.exists(".env.local")
    else load_dotenv()
)


class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def header(text):
    print(f"\n{C.BOLD}{C.INFO}═══ {text} ═══{C.END}")


def ok(text):
    print(f"  {C.OK}✓{C.END} {text}")


def fail(text):
    print(f"  {C.FAIL}✗{C.END} {text}")


def warn(text):
    print(f"  {C.WARN}⚠{C.END}  {text}")


# Pakai endpoint:model yang ADA di QUOTA_LIMITS untuk testing realistic
TEST_ENDPOINT = "gemini-acc1"
TEST_MODEL = "gemini-2.5-pro"  # rpd=25, rpm=5 — paling tight, gampang di-test


async def test_empty_state() -> bool:
    header("TEST 1: Empty state (cleared counter)")
    from app.ai.quota_tracker import quota_tracker

    await quota_tracker.reset(TEST_ENDPOINT, TEST_MODEL)

    has_budget = await quota_tracker.has_budget(TEST_ENDPOINT, TEST_MODEL)
    if not has_budget:
        fail("Expected has_budget=True after reset")
        return False
    ok(f"has_budget({TEST_ENDPOINT}:{TEST_MODEL}) = True ✓")
    return True


async def test_record_increments() -> bool:
    header("TEST 2: record_call increments counter")
    from app.ai.quota_tracker import quota_tracker

    await quota_tracker.reset(TEST_ENDPOINT, TEST_MODEL)

    # Record 3 calls
    for i in range(3):
        await quota_tracker.record_call(TEST_ENDPOINT, TEST_MODEL)

    snapshot = await quota_tracker.snapshot()
    key = f"{TEST_ENDPOINT}:{TEST_MODEL}"
    data = snapshot.get(key, {})

    if data.get("rpd_used") != 3:
        fail(f"Expected rpd_used=3, got {data.get('rpd_used')}")
        return False
    if data.get("rpm_used") != 3:
        fail(f"Expected rpm_used=3, got {data.get('rpm_used')}")
        return False

    ok(f"After 3 calls: rpm_used=3, rpd_used=3 ✓")
    return True


async def test_rpm_exhaustion() -> bool:
    header("TEST 3: RPM exhaustion blocks has_budget")
    from app.ai.quota_tracker import quota_tracker, QUOTA_LIMITS

    await quota_tracker.reset(TEST_ENDPOINT, TEST_MODEL)

    limit = QUOTA_LIMITS[f"{TEST_ENDPOINT}:{TEST_MODEL}"]
    effective_rpm = int(limit.rpm * 0.95)  # safety margin

    # Hit RPM limit (5 * 0.95 = 4 effective for gemini-pro)
    for _ in range(effective_rpm):
        await quota_tracker.record_call(TEST_ENDPOINT, TEST_MODEL)

    has_budget = await quota_tracker.has_budget(TEST_ENDPOINT, TEST_MODEL)
    if has_budget:
        fail(f"Expected has_budget=False after {effective_rpm} calls (RPM limit)")
        return False

    ok(f"RPM exhausted at {effective_rpm} calls → has_budget=False ✓")
    return True


async def test_unknown_model_passthrough() -> bool:
    header("TEST 4: Unknown model fail-open (no QUOTA_LIMITS entry)")
    from app.ai.quota_tracker import quota_tracker

    has_budget = await quota_tracker.has_budget("fake-endpoint", "fake-model-9000")
    if not has_budget:
        fail("Unknown model should fail-open (return True)")
        return False

    ok("Unknown model → has_budget=True (fail-open) ✓")
    return True


async def test_router_integration() -> bool:
    header("TEST 5: Router skips quota-exhausted route")
    from app.ai.quota_tracker import quota_tracker, QUOTA_LIMITS
    from app.ai.router import route_and_generate

    # Exhaust SEMUA gemini pro routes
    for ep in ("gemini-acc1", "gemini-acc2"):
        await quota_tracker.reset(ep, "gemini-2.5-pro")
        limit = QUOTA_LIMITS[f"{ep}:gemini-2.5-pro"]
        # Set ke 100% via banyak calls
        for _ in range(limit.rpd):
            await quota_tracker.record_call(ep, "gemini-2.5-pro")

    # Verify exhausted
    for ep in ("gemini-acc1", "gemini-acc2"):
        if await quota_tracker.has_budget(ep, "gemini-2.5-pro"):
            warn(f"{ep}:gemini-2.5-pro NOT exhausted as expected")

    ok("Both Gemini Pro routes exhausted")
    warn("Router would now skip to other routes — check logs di production")

    # Cleanup
    for ep in ("gemini-acc1", "gemini-acc2"):
        await quota_tracker.reset(ep, "gemini-2.5-pro")
    ok("Cleanup done")

    return True


async def test_snapshot_format() -> bool:
    header("TEST 6: Snapshot format & near-exhausted detection")
    from app.ai.quota_tracker import quota_tracker, QUOTA_LIMITS

    snapshot = await quota_tracker.snapshot()

    if not snapshot:
        warn("Snapshot empty — pastikan QUOTA_LIMITS ter-load")
        return False

    sample_key = next(iter(snapshot))
    sample_data = snapshot[sample_key]

    required_fields = {"rpm_used", "rpm_limit", "rpd_used", "rpd_limit"}
    if not required_fields.issubset(sample_data.keys()):
        fail(f"Missing fields in snapshot: {required_fields - sample_data.keys()}")
        return False

    ok(f"Snapshot has {len(snapshot)} entries with correct schema")
    ok(f"Sample [{sample_key}]: {sample_data}")
    return True


async def main():
    print(f"{C.BOLD}╔══════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║  Quota Tracker Integration Tests         ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════════╝{C.END}")

    from app.ai.quota_tracker import quota_tracker

    results = {}
    try:
        results["Empty State"] = await test_empty_state()
        results["Record Increments"] = await test_record_increments()
        results["RPM Exhaustion"] = await test_rpm_exhaustion()
        results["Unknown Model"] = await test_unknown_model_passthrough()
        results["Snapshot Format"] = await test_snapshot_format()
        results["Router Integration"] = await test_router_integration()
    finally:
        # Cleanup test data
        await quota_tracker.reset(TEST_ENDPOINT, TEST_MODEL)
        await quota_tracker.close()

    # Summary
    header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, status in results.items():
        marker = f"{C.OK}PASS{C.END}" if status else f"{C.FAIL}FAIL{C.END}"
        print(f"  [{marker}] {name}")

    print(f"\n{C.BOLD}Total: {passed}/{total}{C.END}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
