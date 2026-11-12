"""
Send a message to a specific user (PV).

Usage:
    python 01_send_to_user.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    # start() now waits until client is fully ready
    await client.start()

    user_id = 1780245516
    message = "Hello from JetraUserAPI!"

    print(f"Sending to user {user_id}...")
    await client.send_message(user_id, message, peer_type="user")
    print("Message sent successfully!")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
