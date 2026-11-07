"""
A bot that responds to specific commands like /start, /help, /ping.

Usage:
    python 09_command_bot.py
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
        text = message.text.strip().lower()

        if text == "/start":
            reply = "Hello! I am a Jetra bot.\nUse /help to see commands."
            await client.send_message(message.peer_id, reply)

        elif text == "/help":
            reply = (
                "Available commands:\n"
                "/start - Start the bot\n"
                "/help - Show this message\n"
                "/ping - Test bot response\n"
                "/time - Show current time"
            )
            await client.send_message(message.peer_id, reply)

        elif text == "/ping":
            await client.send_message(message.peer_id, "pong")

        elif text == "/time":
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await client.send_message(message.peer_id, f"Current time: {now}")

    print("Command bot is running... Press Ctrl+C to stop.")
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
