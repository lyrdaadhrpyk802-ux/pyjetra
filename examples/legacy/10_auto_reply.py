"""
Auto-reply bot with keyword-based responses.

Usage:
    python 10_auto_reply.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


# Keyword-based responses
RESPONSES = {
    "hello": "Hi there! How can I help you?",
    "hi": "Hello!",
    "bye": "Goodbye! See you later.",
    "thanks": "You're welcome!",
    "ping": "pong",
    "how are you": "I'm just a bot, but I'm doing great!",
}


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    @client.on_message
    async def on_message(message):
        text_lower = message.text.strip().lower()

        # Find matching response
        for keyword, response in RESPONSES.items():
            if keyword in text_lower:
                await client.send_message(message.peer_id, response)
                print(f"Auto-replied to '{message.text}' with '{response}'")
                break

    print("Auto-reply bot is running... Press Ctrl+C to stop.")
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
