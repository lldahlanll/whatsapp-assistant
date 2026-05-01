# test_aimodel.py
"""
Test suite untuk WhatsApp AI Bot.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

# Load .env dulu — sebelum import modul yang baca config
load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()

# Import setelah env loaded
from app.config import settings
from app.ai.router import classify_message, route_and_generate
from app.ai.models import ModelTier, MODELS, TIER_CONFIGS, get_fallback_routes
from app.ai.client import multi_client
from app.ai.circuit_breaker import CircuitBreaker
from app.memory.manager import memory_manager
from app.utils.locks import jid_lock_manager


# ── ANSI colors ───────────────────────────────────────────────
class C:
    OK = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def header(text: str) -> None:
    print(f"\n{C.BOLD}{C.INFO}═══ {text} ═══{C.END}")


def ok(text: str) -> None:
    print(f"  {C.OK}✓{C.END} {text}")


def fail(text: str) -> None:
    print(f"  {C.FAIL}✗{C.END} {text}")


def warn(text: str) -> None:
    print(f"  {C.WARN}⚠{C.END}  {text}")


# ──────────────────────────────────────────────────────────────
# TEST 1: Config
# ──────────────────────────────────────────────────────────────

async def test_config() -> bool:
    header("TEST CONFIG")

    try:
        ok(f"Bot name: {settings.bot_name}")
        ok(f"Session: {settings.session_name}")
        ok(f"Redis URL: {settings.redis_url}")
        ok(f"Max history: {settings.max_history_messages}")
        ok(f"Rate limit: {settings.rate_limit_max}/{settings.rate_limit_window_seconds}s")

        # Cek API keys yang terisi
        keys_status = {
            "Groq":          bool(settings.groq_api_key),
            "Gemini Acc 1":  bool(settings.gemini_api_key_1),
            "Gemini Acc 2":  bool(settings.gemini_api_key_2),
            "OpenRouter 1":  bool(settings.openrouter_api_key_1),
            "OpenRouter 2":  bool(settings.openrouter_api_key_2),
        }

        configured = sum(keys_status.values())
        for name, has_key in keys_status.items():
            marker = "✓" if has_key else "✗"
            color = C.OK if has_key else C.WARN
            print(f"    {color}{marker}{C.END} {name}")

        if configured == 0:
            fail("Tidak ada API key yang dikonfigurasi!")
            return False

        ok(f"Total {configured}/5 API keys configured")
        return True
    except Exception as e:
        fail(f"Config error: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# TEST 2: Provider Registration
# ──────────────────────────────────────────────────────────────

async def test_providers() -> bool:
    header("TEST PROVIDER REGISTRATION")

    status = multi_client.status()

    if status["total"] == 0:
        fail("No providers registered — cek API keys di .env")
        return False

    ok(f"Total providers registered: {status['total']}/5")
    for ep_name in status["registered_endpoints"]:
        ok(f"  • {ep_name}")

    return True


# ──────────────────────────────────────────────────────────────
# TEST 3: Classifier
# ──────────────────────────────────────────────────────────────

async def test_classifier() -> bool:
    header("TEST CLASSIFIER")

    test_cases = [
        ("halo", ModelTier.TIER_1, "greeting pendek"),
        ("apa kabar bro", ModelTier.TIER_1, "casual chat"),
        ("kenapa langit berwarna biru?", ModelTier.TIER_2, "keyword 'kenapa'"),
        ("tolong jelaskan perbedaan docker dan vm", ModelTier.TIER_3, "keyword 'jelaskan'+'docker'"),
        ("buatkan kode python untuk scraping", ModelTier.TIER_3, "keyword 'kode'+'python'"),
        ("a" * 250, ModelTier.TIER_2, "medium length"),
        ("a" * 600, ModelTier.TIER_3, "very long"),
        ("dudewhatsupcode", ModelTier.TIER_1, "no word boundary match"),
    ]

    all_pass = True
    for text, expected, label in test_cases:
        result = classify_message(text)
        preview = text[:40] + "..." if len(text) > 40 else text
        if result == expected:
            ok(f"{label}: '{preview}' → {result.name}")
        else:
            fail(f"{label}: '{preview}' → {result.name} (expected: {expected.name})")
            all_pass = False

    return all_pass


# ──────────────────────────────────────────────────────────────
# TEST 4: Fallback Routes
# ──────────────────────────────────────────────────────────────

async def test_fallback_routes() -> bool:
    header("TEST FALLBACK ROUTES")

    for tier in (ModelTier.TIER_3, ModelTier.TIER_2, ModelTier.TIER_1):
        routes = get_fallback_routes(tier)
        if not routes:
            fail(f"{tier.name}: no routes")
            return False

        # Group by provider untuk show diversifikasi
        providers_used = {r.provider_type.value for r in routes}
        ok(f"{tier.name}: {len(routes)} routes via {sorted(providers_used)}")
        for r in routes[:3]:
            print(f"      → {r.name}")
        if len(routes) > 3:
            print(f"      → ... +{len(routes) - 3} more")

    return True


# ──────────────────────────────────────────────────────────────
# TEST 5: Circuit Breaker
# ──────────────────────────────────────────────────────────────

async def test_circuit_breaker() -> bool:
    header("TEST CIRCUIT BREAKER")

    cb = CircuitBreaker(disable_duration=2)
    model_id = "test/model:free"

    if await cb.is_open(model_id):
        fail("Initial state harusnya closed")
        return False
    ok("Initial state: closed")

    await cb.trip(model_id, reason="HTTP 404")
    if not await cb.is_open(model_id):
        fail("After trip harusnya open")
        return False
    ok("After trip: open")

    print("    Waiting 2.5s untuk auto-reset...")
    await asyncio.sleep(2.5)
    if await cb.is_open(model_id):
        fail("Setelah duration habis, harusnya closed")
        return False
    ok("Auto-reset works")

    await cb.trip(model_id, reason="test")
    await cb.reset(model_id)
    if await cb.is_open(model_id):
        fail("Manual reset tidak bekerja")
        return False
    ok("Manual reset works")

    return True


# ──────────────────────────────────────────────────────────────
# TEST 6: Per-JID Lock
# ──────────────────────────────────────────────────────────────

async def test_jid_lock() -> bool:
    header("TEST PER-JID LOCK")

    jid_a = "628111@s.whatsapp.net"
    jid_b = "628222@s.whatsapp.net"
    execution_order: list[str] = []

    async def task(jid: str, label: str, delay: float):
        async with jid_lock_manager.acquire(jid, timeout=10.0):
            execution_order.append(f"{label}-start")
            await asyncio.sleep(delay)
            execution_order.append(f"{label}-end")

    # Same JID → sequential
    execution_order.clear()
    await asyncio.gather(
        task(jid_a, "A1", 0.1),
        task(jid_a, "A2", 0.1),
    )
    is_seq = (
        execution_order == ["A1-start", "A1-end", "A2-start", "A2-end"]
        or execution_order == ["A2-start", "A2-end", "A1-start", "A1-end"]
    )
    if is_seq:
        ok(f"Same JID sequential: {execution_order}")
    else:
        fail(f"Same JID INTERLEAVED: {execution_order}")
        return False

    # Different JID → paralel
    execution_order.clear()
    await asyncio.gather(
        task(jid_a, "A", 0.2),
        task(jid_b, "B", 0.2),
    )
    is_parallel = execution_order[:2] in (
        ["A-start", "B-start"],
        ["B-start", "A-start"],
    )
    if is_parallel:
        ok(f"Different JID paralel: {execution_order}")
    else:
        fail(f"Different JID NOT paralel: {execution_order}")
        return False

    return True


# ──────────────────────────────────────────────────────────────
# TEST 7: Memory Manager
# ──────────────────────────────────────────────────────────────

async def test_memory() -> bool:
    header("TEST MEMORY MANAGER")

    test_jid = "628123456789@s.whatsapp.net"
    max_history = settings.max_history_messages

    if not await memory_manager.ping():
        fail("Redis ping FAILED — pastikan Redis jalan")
        return False
    ok("Redis ping OK")

    await memory_manager.clear_history(test_jid)
    await memory_manager.add_message(test_jid, "user", "halo bot!")
    await memory_manager.add_message(test_jid, "assistant", "Halo!")
    await memory_manager.add_message(test_jid, "user", "siapa kamu?")
    ok("Added 3 messages")

    history = await memory_manager.get_history(test_jid)
    # ──────────────────────────────────────────────────────
    # CHANGED: dulu expect 4 (system + 3), sekarang 3 saja
    # System prompt sudah dipindah ke router (layered prompting)
    # ──────────────────────────────────────────────────────
    if len(history) != 3:
        fail(f"History count: {len(history)}, expected 3 (no system prompt)")
        return False
    ok(f"History count: {len(history)} (user-assistant only, no system)")

    # Verify isi history benar
    if history[0]["role"] != "user" or history[0]["content"] != "halo bot!":
        fail(f"First msg salah: {history[0]}")
        return False
    if history[-1]["role"] != "user" or history[-1]["content"] != "siapa kamu?":
        fail(f"Last msg salah: {history[-1]}")
        return False
    ok("History order & content correct")

    stats = await memory_manager.get_stats(test_jid)
    if stats.get("message_count") != 3:
        fail(f"Stats invalid: {stats}")
        return False
    ok(f"Stats: {stats['message_count']} msgs, TTL {stats['ttl_hours']}h")

    await memory_manager.save_meta(test_jid, "Test User", False)
    meta = await memory_manager.get_meta(test_jid)
    if not meta or meta.get("push_name") != "Test User":
        fail(f"Meta failed: {meta}")
        return False
    ok(f"Meta saved: {meta['push_name']}")

    await memory_manager.clear_history(test_jid)

    # Verify clear works — sekarang harus 0 (bukan 1 seperti sebelumnya)
    history_after = await memory_manager.get_history(test_jid)
    if len(history_after) != 0:
        fail(f"After clear: {len(history_after)} items (expected 0)")
        return False
    ok("After clear: empty (no system prompt anymore)")

    # Trim test
    print(f"    Testing trim (MAX_HISTORY={max_history})...")
    for i in range(max_history + 5):
        await memory_manager.add_message(test_jid, "user", f"msg-{i+1}")
    trimmed = await memory_manager.get_history(test_jid)
    # ──────────────────────────────────────────────────────
    # CHANGED: dulu expect max_history + 1, sekarang max_history saja
    # ──────────────────────────────────────────────────────
    if len(trimmed) != max_history:
        fail(f"Trim failed: {len(trimmed)} (expected {max_history})")
        return False
    ok(f"Trim works: {len(trimmed)} msgs (max {max_history})")

    # Rate limit
    test_rl = "628999999999@s.whatsapp.net"
    r = await memory_manager._get_redis()
    await r.delete(f"ratelimit:{test_rl}")

    limited_at = None
    for i in range(5):
        is_limited = await memory_manager.is_rate_limited(
            test_rl, limit=3, window_seconds=10
        )
        if is_limited and limited_at is None:
            limited_at = i + 1

    if limited_at == 4:
        ok(f"Rate limiter triggered at msg #{limited_at}")
    else:
        fail(f"Rate limit at #{limited_at} (expected 4)")
        return False

    await memory_manager.clear_history(test_jid)
    await r.delete(f"ratelimit:{test_rl}")
    return True


# ──────────────────────────────────────────────────────────────
# TEST 8: API Call (real call, optional)
# ──────────────────────────────────────────────────────────────

async def test_api_call() -> bool:
    header("TEST API CALL (live)")

    if multi_client.status()["total"] == 0:
        warn("No providers registered — skip")
        return True

    from app.ai.prompts import ChatContext

    print("    Sending test message dengan context...")
    history = [{"role": "user", "content": "Halo, kenalkan nama kamu siapa?"}]
    context = ChatContext(push_name="Tester", is_group=False)

    response, route_used = await route_and_generate(
        history=history,
        user_text="Halo, kenalkan nama kamu siapa?",
        context=context,
    )

    if response:
        ok(f"Response: '{response[:100]}...'")
        ok(f"Route used: {route_used}")
        # Bonus: cek apakah persona "Nara" muncul
        if "nara" in response.lower():
            ok("Persona 'Nara' muncul di response! 🎯")
        else:
            warn("Persona 'Nara' tidak muncul (bisa OK kalau model decline introduce)")
        return True
    else:
        warn("Semua route gagal")
        return False


# ──────────────────────────────────────────────────────────────
# TEST 9: TEST PROMPT
# ──────────────────────────────────────────────────────────────
async def test_prompt_composition() -> bool:
    header("TEST PROMPT COMPOSITION")

    from app.ai.prompts import (
        BASE_PERSONA,
        ChatContext,
        TIER_HINTS,
        build_system_prompt,
        PROMPT_VERSION,
    )
    from app.ai.models import ModelTier

    ok(f"Prompt version: {PROMPT_VERSION}")

    # Test 1: Base persona ada konten
    if len(BASE_PERSONA) < 500:
        fail(f"BASE_PERSONA too short: {len(BASE_PERSONA)} chars")
        return False
    ok(f"Base persona: {len(BASE_PERSONA)} chars")

    # Test 2: Semua tier punya hint
    for tier in ModelTier:
        if tier not in TIER_HINTS:
            fail(f"Missing hint for {tier.name}")
            return False
    ok(f"All {len(TIER_HINTS)} tiers have hints")

    # Test 3: Build prompt tanpa context
    prompt_no_ctx = build_system_prompt(ModelTier.TIER_1)
    if "Nama user" in prompt_no_ctx:
        fail("Prompt should NOT include context when context=None")
        return False
    ok(f"Tier 1 prompt (no ctx): {len(prompt_no_ctx)} chars")

    # Test 4: Build prompt dengan context private
    ctx = ChatContext(push_name="Budi", is_group=False)
    prompt_private = build_system_prompt(ModelTier.TIER_2, ctx)
    assertions = [
        ("Budi" in prompt_private, "user name harus muncul"),
        ("PRIVATE" in prompt_private, "tipe chat harus muncul"),
        ("Mode Standar" in prompt_private, "tier 2 hint harus muncul"),
    ]
    for cond, msg in assertions:
        if not cond:
            fail(msg)
            return False
    ok(f"Tier 2 prompt (private): {len(prompt_private)} chars")

    # Test 5: Build prompt dengan context group
    ctx_group = ChatContext(push_name="Andi", is_group=True)
    prompt_group = build_system_prompt(ModelTier.TIER_3, ctx_group)
    if "GROUP" not in prompt_group:
        fail("Group context tidak muncul")
        return False
    if "Mode Mendalam" not in prompt_group:
        fail("Tier 3 hint tidak muncul")
        return False
    ok(f"Tier 3 prompt (group): {len(prompt_group)} chars")

    # Test 6: Time-of-day context
    if not any(t in prompt_private for t in ["pagi", "siang", "sore", "malam"]):
        fail("Time context tidak ter-inject")
        return False
    ok("Time-of-day context bekerja")

    return True

# ──────────────────────────────────────────────────────────────
# TEST 10: TEST FREE TIER
# ──────────────────────────────────────────────────────────────    

async def test_free_tier_safety() -> bool:
    header("TEST FREE-TIER SAFETY")

    from app.ai.models import assert_free_tier_only, TIER_CONFIGS

    try:
        assert_free_tier_only()
        ok("All routes verified as FREE tier")
    except AssertionError as e:
        fail(f"Free tier check failed: {e}")
        return False

    # Bonus: tampilkan ringkasan
    total_routes = sum(len(c.routes) for c in TIER_CONFIGS.values())
    ok(f"Total routes verified: {total_routes}")

    # Cek tidak ada route OpenRouter yang miss :free
    or_routes = [
        r for cfg in TIER_CONFIGS.values()
        for r in cfg.routes
        if r.provider_type.value == "openrouter"
    ]
    or_paid = [r for r in or_routes if not r.model_id.endswith(":free")]
    if or_paid:
        fail(f"OpenRouter paid routes found: {[r.name for r in or_paid]}")
        return False
    ok(f"All {len(or_routes)} OpenRouter routes use ':free' suffix")

    return True


# ──────────────────────────────────────────────────────────────
# Main runner
# ──────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"{C.BOLD}╔══════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}║   WhatsApp AI Bot — Test Suite       ║{C.END}")
    print(f"{C.BOLD}╚══════════════════════════════════════╝{C.END}")

    results: dict[str, bool] = {}

    try:
        results["Config"]          = await test_config()
        results["Providers"]       = await test_providers()
        results["Free-Tier Safety"]  = await test_free_tier_safety()
        results["Classifier"]      = await test_classifier()
        results["Fallback Routes"] = await test_fallback_routes()
        results["Circuit Breaker"] = await test_circuit_breaker()
        results["JID Lock"]        = await test_jid_lock()
        results["Memory Manager"]  = await test_memory()
        results["API Call"]        = await test_api_call()
        results["Prompt Composition"] = await test_prompt_composition()
    finally:
        await multi_client.close()
        await memory_manager.close()

    # Summary
    header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, status in results.items():
        marker = f"{C.OK}PASS{C.END}" if status else f"{C.FAIL}FAIL{C.END}"
        print(f"  [{marker}] {name}")

    print(f"\n{C.BOLD}Total: {passed}/{total} passed{C.END}")

    if passed == total:
        print(f"{C.OK}{C.BOLD}✓ All tests passed!{C.END}\n")
        sys.exit(0)
    else:
        print(f"{C.FAIL}{C.BOLD}✗ Some tests failed{C.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())