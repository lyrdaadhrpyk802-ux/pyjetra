"""
Listen for all incoming messages and print them.

Usage:
    python 07_listen_messages.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    @client.on_message
    async def on_message(message):
        peer_label = "PV" if message.is_private else "Group"

        print(f"\n[{peer_label}]")
        print(f"  From: {message.from_id}")
        print(f"  Time: {message.date_str}")
        print(f"  Text: {message.text}")

    print("Listening for messages... Press Ctrl+C to stop.")
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
