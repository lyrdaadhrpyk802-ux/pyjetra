# ============================================
#  examples/04_user_basics/02_send_message.py - Send a text message as a user
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Run 01_login.py first to create a session.
#
#  Run:
#    python examples/04_user_basics/02_send_message.py <peer_id> "your message"
#    python examples/04_user_basics/02_send_message.py 123456789 "سلام"
# ============================================
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    if len(sys.argv) < 3:
        print("usage: python 02_send_message.py <peer_id> <text>")
        print("  peer_id: user or group id (integer)")
        print("  text:     message text (quote it)")
        return 2

    try:
        peer_id = int(sys.argv[1])
    except ValueError:
        print(f"[error] peer_id must be an integer, got: {sys.argv[1]}")
        return 2

    text = sys.argv[2]

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        # peer_type is auto-detected from the local dialog database.
        msg_id = await client.send_message(peer_id, text)
        print(f"[ok] message sent, msg_id={msg_id}")
        return 0
    except JetraError as e:
        print(f"[error] send_message failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
