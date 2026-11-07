"""
List all your groups.

Usage:
    python 04_list_groups.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    @client.on_ready
    async def on_ready():
        groups = await client.get_groups()

        print(f"\nYou are a member of {len(groups)} groups:\n")
        for i, g in enumerate(groups, 1):
            print(f"  {i}. {g['title']}")
            print(f"     ID: {g['peer_id']}")

    await client.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
