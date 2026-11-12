"""
Send a message to Saved Messages (yourself).

Usage:
    python 03_send_to_saved.py
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

    message = "Note to self: buy milk"

    print("Sending to Saved Messages...")
    await client.send_to_saved(message)
    print("Message sent successfully!")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
