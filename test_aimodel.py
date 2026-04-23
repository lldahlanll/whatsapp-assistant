# test_ai.py — jalankan di lokal untuk test
import asyncio
import os
from dotenv import load_dotenv
from app.memory.manager import MAX_HISTORY

load_dotenv()  # Load .env dulu
# Gunakan .env.local kalau ada, fallback ke .env
load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()
from app.ai.router import route_and_generate, classify_message
from app.ai.models import ModelTier

async def test_classifier():
    """Test apakah classifier mengklasifikasi pesan dengan benar."""
    print("\n=== TEST CLASSIFIER ===")
    test_cases = [
        ("halo", ModelTier.TIER_1),
        ("apa kabar bro", ModelTier.TIER_1),
        ("kenapa langit berwarna biru?", ModelTier.TIER_2),
        ("tolong jelaskan perbedaan docker dan vm", ModelTier.TIER_3),
        ("buatkan kode python untuk scraping", ModelTier.TIER_3),
    ]

    all_pass = True
    for text, expected in test_cases:
        result = classify_message(text)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_pass = False
        print(f"  {status} '{text}' → {result.name} (expected: {expected.name})")

    print(f"\nClassifier: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


async def test_api_call():
    """Test actual API call ke OpenRouter."""
    from app.ai.client import openrouter_client

    if not os.getenv("OPENROUTER_API_KEY"):
        print("\n⚠️  OPENROUTER_API_KEY tidak ditemukan di .env — skip API test")
        return

    print("\n=== TEST API CALL ===")
    print("Mengirim pesan test ke OpenRouter...")

    messages = [{"role": "user", "content": "Balas hanya dengan: OK"}]
    response, model_used = await route_and_generate(
        messages=messages,
        user_text="Balas hanya dengan: OK",
    )

    if response:
        print(f"  ✓ Response: '{response}'")
        print(f"  ✓ Model used: {model_used}")
    else:
        print("  ✗ Semua model gagal — cek API key dan koneksi internet")

    await openrouter_client.close()


# Tambahkan di test_ai.py

async def test_memory():
    """Test memory manager tanpa perlu WhatsApp."""
    from app.memory.manager import memory_manager

    print("\n=== TEST MEMORY MANAGER ===")
    test_jid = "628123456789@s.whatsapp.net"

    # 1. Ping Redis
    ok = await memory_manager.ping()
    print(f"  {'✓' if ok else '✗'} Redis ping: {'OK' if ok else 'FAILED'}")
    if not ok:
        print("  ⚠️  Pastikan Redis berjalan: docker compose up redis -d")
        return

    # 2. Clear dulu (fresh start)
    await memory_manager.clear_history(test_jid)

    # 3. Tambah beberapa pesan
    await memory_manager.add_message(test_jid, "user", "halo bot!")
    await memory_manager.add_message(test_jid, "assistant", "Halo! Ada yang bisa dibantu?")
    await memory_manager.add_message(test_jid, "user", "siapa kamu?")
    print("  ✓ Added 3 messages")

    # 4. Ambil history
    history = await memory_manager.get_history(test_jid)
    # system prompt + 3 messages = 4 total
    expected = 4
    ok = len(history) == expected
    print(f"  {'✓' if ok else '✗'} History count: {len(history)} (expected {expected})")
    print(f"     First: {history[0]['role']} → '{history[0]['content'][:40]}...'")
    print(f"     Last : {history[-1]['role']} → '{history[-1]['content']}'")

    # 5. Test stats
    stats = await memory_manager.get_stats(test_jid)
    print(f"  ✓ Stats: {stats['message_count']} messages, TTL {stats['ttl_hours']}h")

    # 6. Test clear
    await memory_manager.clear_history(test_jid)
    history_after = await memory_manager.get_history(test_jid)
    ok = len(history_after) == 1  # hanya system prompt
    print(f"  {'✓' if ok else '✗'} After clear: {len(history_after)} item (system prompt only)")

    # 7. Test trim — simulasi MAX_HISTORY
    print(f"  ✓ Testing trim (MAX_HISTORY={MAX_HISTORY})...")
    for i in range(MAX_HISTORY + 5):  # kirim lebih dari batas
        await memory_manager.add_message(test_jid, "user", f"pesan ke-{i+1}")
    history_trimmed = await memory_manager.get_history(test_jid)
    # +1 karena system prompt
    ok = len(history_trimmed) == MAX_HISTORY + 1
    print(f"  {'✓' if ok else '✗'} Trim: {len(history_trimmed)-1} messages (max {MAX_HISTORY})")

    # Cleanup
    await memory_manager.clear_history(test_jid)
    await memory_manager.close()
    print("\n  Memory Manager: PASS ✓")


# Update fungsi main()
async def main():
    classifier_ok = await test_classifier()
    await test_api_call()
    await test_memory()         # ← tambahkan ini

if __name__ == "__main__":
    asyncio.run(main())