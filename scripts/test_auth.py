# scripts/cek_auth.py
"""
Inspect auth data di Redis (mirror dari cek_redis.py).

Tampilkan:
- Whitelist users
- Active sessions
- Stored credentials (encrypted blob, tidak decrypt)

Run dari root project: python scripts/cek_auth.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent dir ke sys.path agar bisa import app.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(".env.local", override=True) if os.path.exists(".env.local") else load_dotenv()

import redis.asyncio as aioredis

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


class C:
    OK = "\033[92m"
    INFO = "\033[94m"
    WARN = "\033[93m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


async def main():
    r_str = await aioredis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
        encoding="utf-8",
        decode_responses=True,
    )
    r_bin = await aioredis.from_url(
        f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
        decode_responses=False,
    )

    print(f"\n{C.BOLD}🔐 AUTH INSPECTOR{C.END}")
    print("=" * 60)

    # ── Admin from .env ───────────────────────────────────────
    admin_jids = os.getenv("ADMIN_JIDS", "")
    print(f"\n{C.BOLD}👑 ADMINS (from .env){C.END}")
    print("─" * 60)
    if admin_jids:
        for jid in admin_jids.split(","):
            print(f"  • {jid.strip()}")
    else:
        print(f"  {C.WARN}⚠️  ADMIN_JIDS belum diset{C.END}")

    # ── Whitelist Users ───────────────────────────────────────
    print(f"\n{C.BOLD}👥 WHITELIST USERS{C.END}")
    print("─" * 60)
    users = await r_str.hgetall("whitelist:users")
    if not users:
        print(f"  {C.DIM}(belum ada user di whitelist){C.END}")
    else:
        for jid, payload in users.items():
            try:
                info = json.loads(payload)
                added_at = datetime.fromtimestamp(info["added_at"]).strftime("%Y-%m-%d %H:%M")
                print(f"  • {C.OK}{info['display_name']}{C.END}")
                print(f"      JID       : {jid}")
                print(f"      Ditambah  : {added_at}")
                print(f"      Oleh      : {info['added_by']}")
            except Exception as e:
                print(f"  ⚠️  {jid}: corrupt data ({e})")

    # ── Active Sessions ───────────────────────────────────────
    print(f"\n{C.BOLD}🔓 ACTIVE SESSIONS{C.END}")
    print("─" * 60)
    session_keys = await r_str.keys("session:*")
    if not session_keys:
        print(f"  {C.DIM}(tidak ada session aktif){C.END}")
    else:
        now = time.time()
        for key in session_keys:
            jid = key.replace("session:", "")
            raw = await r_str.get(key)
            if raw:
                data = json.loads(raw)
                remaining = data["expires_at"] - now
                if remaining > 0:
                    h = int(remaining // 3600)
                    m = int((remaining % 3600) // 60)
                    created = datetime.fromtimestamp(data["created_at"]).strftime("%H:%M")
                    print(f"  • {C.OK}{data['email']}{C.END}")
                    print(f"      JID       : {jid}")
                    print(f"      Login     : {created}")
                    print(f"      Sisa      : {h}h {m}m")
                else:
                    print(f"  • {C.DIM}{jid}: EXPIRED (akan auto-cleanup){C.END}")

    # ── Stored Credentials ────────────────────────────────────
    print(f"\n{C.BOLD}🔑 STORED CREDENTIALS (encrypted){C.END}")
    print("─" * 60)
    cred_keys = await r_bin.keys(b"creds:*")
    if not cred_keys:
        print(f"  {C.DIM}(belum ada credential tersimpan){C.END}")
    else:
        for key in cred_keys:
            jid = key.decode().replace("creds:", "")
            raw = await r_bin.get(key)
            ttl = await r_bin.ttl(key)
            ttl_days = ttl // 86400 if ttl > 0 else 0
            preview = raw[:40].decode("utf-8", errors="replace")
            print(f"  • JID       : {jid}")
            print(f"    TTL       : {ttl_days} hari tersisa")
            print(f"    Encrypted : {preview}...")
            print(f"    {C.OK}✓ Tidak ada plaintext (Fernet encryption){C.END}")

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{C.BOLD}📊 SUMMARY{C.END}")
    print("─" * 60)
    n_admins = len(admin_jids.split(",")) if admin_jids else 0
    n_users = len(users)
    n_sessions = len(session_keys)
    n_creds = len(cred_keys)

    print(f"  Admins      : {n_admins}")
    print(f"  Whitelist   : {n_users} user(s)")
    print(f"  Active      : {n_sessions} session(s)")
    print(f"  Stored creds: {n_creds}")
    print()

    await r_str.aclose()
    await r_bin.aclose()


if __name__ == "__main__":
    asyncio.run(main())