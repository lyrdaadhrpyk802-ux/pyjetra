# ============================================
#  examples/04_user_basics/03_listen_messages.py - Listen for incoming messages
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Run 01_login.py first to create a session.
#
#  Run:
#    python examples/04_user_basics/03_listen_messages.py
# ============================================
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)


@client.on_message()
async def on_msg(message):
    """Print every incoming message."""
    # message.peer_type is "user" or "group"
    # message.from_id is the sender's user_id
    # message.text is the message body (may be empty for media)
    print(f"[{message.peer_type}] from={message.from_id} peer={message.peer_id}")
    if message.text:
        print(f"  text: {message.text}")
    if message.is_reply:
        print(f"  reply to msg_id={message.reply_to_msg_id}")


@client.on_message(peer_type="user")
async def on_private(message):
    """Only fires for private chats."""
    print(f"  -> private message from user_id={message.from_id}")


@client.on_message(peer_type="group")
async def on_group(message):
    """Only fires for group/channel messages."""
    print(f"  -> group message in peer_id={message.peer_id}")


@client.on_ready
def ready():
    """Called once when the client is fully synced and listening."""
    print("[ready] listening for messages ... press Ctrl+C to stop")


async def main():
    await client.start()
    # Run forever; Ctrl+C will cancel the loop.
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
        print("\nstopped")
