# scripts/compare_prompts.py
"""
Manual A/B testing — compare prompt response side-by-side.
Run: python scripts/compare_prompts.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.ai.client import multi_client
from app.ai.models import ModelTier, get_fallback_routes
from app.ai.prompts import ChatContext, build_system_prompt


# Old prompt (versi sebelumnya)
OLD_PROMPT = """Kamu adalah asisten AI yang membantu dan ramah, 
diintegrasikan ke WhatsApp. Jawab dalam bahasa yang sama dengan 
yang digunakan user. Jawab secara ringkas dan jelas. 
Jangan menyebut dirimu sebagai model AI tertentu."""


TEST_QUERIES = [
    ("halo", ModelTier.TIER_1),
    ("gimana cara fokus belajar saat banyak distraksi?", ModelTier.TIER_2),
    ("buatkan template email follow-up ke client yang ga balas", ModelTier.TIER_2),
    ("jelaskan perbedaan async vs threading di python", ModelTier.TIER_3),
]


async def query_with_prompt(system_prompt: str, user_msg: str, tier: ModelTier) -> str:
    """Send query dengan custom system prompt."""
    routes = get_fallback_routes(tier)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    for route in routes:
        response = await multi_client.call(
            endpoint_name=route.endpoint_name,
            model_id=route.model_id,
            messages=messages,
            max_tokens=route.max_tokens,
        )
        if response:
            return f"[{route.name}]\n{response}"
    return "[FAILED]"


async def main():
    print("\n" + "=" * 70)
    print("  PROMPT A/B TEST — Old vs New (Layered Persona)")
    print("=" * 70)

    for query, tier in TEST_QUERIES:
        print(f"\n{'─' * 70}")
        print(f"📨 USER: {query}")
        print(f"   (tier: {tier.name})")
        print(f"{'─' * 70}")

        # Old prompt
        print("\n🅰️  OLD PROMPT:")
        old_response = await query_with_prompt(OLD_PROMPT, query, tier)
        print(old_response)

        # New prompt with context
        ctx = ChatContext(push_name="Tester", is_group=False)
        new_prompt = build_system_prompt(tier, ctx)
        print("\n🅱️  NEW PROMPT (Nara persona):")
        new_response = await query_with_prompt(new_prompt, query, tier)
        print(new_response)

    await multi_client.close()
    print("\n" + "=" * 70)
    print("  Compare both responses — mana yang lebih baik?")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())