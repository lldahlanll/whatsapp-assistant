import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()

import redis.asyncio as aioredis

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

async def main():
    r = await aioredis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
        encoding="utf-8",
        decode_responses=True,
    )

    print("\n📦 REDIS INSPECTOR\n" + "="*50)

    # 1. Semua keys
    keys = await r.keys("*")
    if not keys:
        print("⚠️  Tidak ada data di Redis.")
        await r.aclose()
        return

    print(f"Total keys: {len(keys)}\n")

    # 2. Tampilkan per JID
    history_keys = [k for k in keys if k.startswith("history:")]

    for hkey in history_keys:
        jid = hkey.replace("history:", "")
        messages = await r.lrange(hkey, 0, -1)
        ttl = await r.ttl(hkey)
        ttl_hari = round(ttl / 86400, 1)

        print(f"👤 JID  : {jid}")
        print(f"   Pesan : {len(messages)} messages | TTL: {ttl_hari} hari tersisa")
        print(f"   {'─'*44}")

        for i, raw in enumerate(messages, 1):
            msg = json.loads(raw)
            role = msg["role"].upper()
            content = msg["content"]
            ts = datetime.fromtimestamp(msg["timestamp"]).strftime("%H:%M:%S")
            # Truncate kalau terlalu panjang
            preview = content[:60] + "..." if len(content) > 60 else content
            icon = "🧑" if role == "USER" else "🤖"
            print(f"   {i:2}. {icon} [{ts}] {role}: {preview}")

        print()

    await r.aclose()

asyncio.run(main())