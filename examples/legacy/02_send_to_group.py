"""
Send a message to a group.

Usage:
    python 02_send_to_group.py
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

    group_id = 2017
    message = "Hello group!"

    print(f"Sending to group {group_id}...")
    await client.send_message(group_id, message, peer_type="group")
    print("Message sent successfully!")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
