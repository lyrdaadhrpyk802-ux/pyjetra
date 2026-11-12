# ============================================
#  examples/99_recipes/03_scheduled_sender.py - Schedule messages for later
#  All code and comments are English. No emojis.
#
#  Two modes:
#    1. Server-side scheduling (Jetra supports schedule_date on sendMessage)
#    2. Client-side scheduling (local asyncio loop, sends at the right time)
#
#  This recipe demonstrates BOTH so you can pick what fits your use case.
#
#  Prerequisites:
#    - Logged in (run 04_user_basics/01_login.py first)
#
#  Run:
#    # Server-side: schedule for a future unix timestamp
#    python 03_scheduled_sender.py server <peer_id> "<text>" <unix_timestamp>
#
#    # Client-side: schedule via local loop, e.g. "in 60 seconds"
#    python 03_scheduled_sender.py client <peer_id> "<text>" <delay_seconds>
# ============================================
import asyncio
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def server_side(client, peer_id, text, schedule_date):
    """Use Jetra's built-in schedule_date parameter."""
    # Note: send_message accepts schedule_date as a unix timestamp.
    # The server keeps the message and delivers it at the scheduled time.
    msg_id = await client.send_message(
        peer_id, text, schedule_date=schedule_date,
    )
    print(f"[server] scheduled msg_id={msg_id} for timestamp {schedule_date}")


async def client_side(client, peer_id, text, delay_seconds):
    """Hold the message locally and send it after delay_seconds."""
    send_at = time.time() + delay_seconds
    wait = send_at - time.time()
    if wait > 0:
        print(f"[client] waiting {wait:.1f}s before sending ...")
        await asyncio.sleep(wait)
    msg_id = await client.send_message(peer_id, text)
    print(f"[client] sent msg_id={msg_id} at {int(time.time())}")


async def main():
    if len(sys.argv) < 5:
        print("usage: python 03_scheduled_sender.py <mode> <peer_id> <text> <time>")
        print("  mode: server | client")
        print("  server: <time> is a unix timestamp (future)")
        print("  client: <time> is delay in seconds from now")
        return 2

    mode = sys.argv[1].lower()
    try:
        peer_id = int(sys.argv[2])
    except ValueError:
        print(f"[error] peer_id must be integer, got: {sys.argv[2]}")
        return 2
    text = sys.argv[3]

    try:
        t = int(sys.argv[4])
    except ValueError:
        print(f"[error] time must be integer, got: {sys.argv[4]}")
        return 2

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        if mode == "server":
            if t <= int(time.time()):
                print("[error] server mode: timestamp must be in the future")
                return 2
            await server_side(client, peer_id, text, t)
        elif mode == "client":
            if t <= 0:
                print("[error] client mode: delay must be positive")
                return 2
            await client_side(client, peer_id, text, t)
        else:
            print(f"[error] unknown mode: {mode}")
            return 2
        return 0
    except JetraError as e:
        print(f"[error] {mode} scheduling failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
