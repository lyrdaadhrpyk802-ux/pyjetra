"""
List all your user contacts.

Usage:
    python 05_list_users.py
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
        users = client.db.get_dialogs("user")

        print(f"\nYou have {len(users)} users in your dialogs:\n")
        for i, u in enumerate(users, 1):
            print(f"  {i}. {u['title']}")
            print(f"     ID: {u['peer_id']}")

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
