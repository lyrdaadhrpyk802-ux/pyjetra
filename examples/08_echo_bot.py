"""
Echo bot: replies with the same message it receives.

Usage:
    python 08_echo_bot.py
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
        print(f"Received: {message.text}")
        reply = f"Echo: {message.text}"
        await client.send_message(message.peer_id, reply)
        print(f"Replied: {reply}")

    print("Echo bot is running... Press Ctrl+C to stop.")
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
