"""CLI Entry point for whatsapp_platform."""

import asyncio

from whatsapp_platform.app import main

if __name__ == "__main__":
    asyncio.run(main())
