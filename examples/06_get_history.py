"""
Get message history from local database.

Usage:
    python 06_get_history.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    print("\nLast 10 messages from all chats:\n")
    history = client.get_history(limit=10)

    for msg in history:
        print(f"  [{msg['peer_type']}] From {msg['from_id']}: {msg['text']}")

    print("\n\nLast 5 messages from group 2017:\n")
    history = client.get_history(peer_id=2017, limit=5)

    for msg in history:
        print(f"  {msg['text']}")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
