import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def main():
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        print("❌ OPENROUTER_API_KEY tidak ada di .env")
        return

    if api_key == "your_openrouter_api_key_here":
        print("❌ API key masih placeholder! Ganti dengan key asli dari openrouter.ai/keys")
        return

    print(f"✓ API key found: {api_key[:15]}...{api_key[-4:]} (length: {len(api_key)})")

    # Test 1: Cek key & credits
    print("\n[1] Cek key & credits...")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        print(f"    Status: {r.status_code}")
        print(f"    Body  : {r.text[:300]}")

    # Test 2: List available free models
    print("\n[2] Cari free models yang tersedia...")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if r.status_code == 200:
            models = r.json().get("data", [])
            free_models = [m for m in models if m["id"].endswith(":free")]
            print(f"    Total free models: {len(free_models)}")
            print(f"    Sample (10 pertama):")
            for m in free_models[:10]:
                ctx = m.get("context_length", "?")
                print(f"      • {m['id']:<60} (ctx: {ctx})")

            # Cek model yang Anda pakai
            print(f"\n    Status model di config Anda:")
            target_models = [
                "arcee-ai/trinity-large-preview:free",
                "openai/gpt-oss-120b:free",
                "nvidia/nemotron-3-super-120b-a12b:free",
            ]
            available_ids = {m["id"] for m in models}
            for tm in target_models:
                status = "✓ AVAILABLE" if tm in available_ids else "✗ NOT FOUND (perlu ganti!)"
                print(f"      {status}: {tm}")
        else:
            print(f"    Failed: {r.status_code} — {r.text[:200]}")

    # Test 3: Actual completion
    print("\n[3] Test completion...")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/whatsapp-ai-bot",
                "X-Title": "WhatsApp AI Bot",
            },
            json={
                "model": "meta-llama/llama-3.2-3b-instruct:free",  # model populer & stabil
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 10,
            },
        )
        print(f"    Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            print(f"    ✓ Response: '{content}'")
            print(f"    ✓ Model bekerja, API key valid!")
        else:
            print(f"    Body: {r.text[:500]}")

asyncio.run(main())
