# ============================================
#  examples/99_recipes/02_group_guard.py - User-API group guard bot
#  All code and comments are English. No emojis.
#
#  Listens for new messages in a group and removes messages from blacklisted
#  users or messages containing forbidden keywords. Requires admin rights.
#
#  Prerequisites:
#    - Logged in (run 04_user_basics/01_login.py first)
#    - Your account must be admin in the target group
#
#  Run:
#    python 02_group_guard.py <group_id> [--ban-bots] [--delete-keyword spam]
# ============================================
import asyncio
import sys
import argparse
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    parser = argparse.ArgumentParser(description="Group guard bot")
    parser.add_argument("group_id", type=int, help="Group to guard")
    parser.add_argument("--ban-bots", action="store_true",
                        help="Kick any bot that joins (not implemented here;)")
    parser.add_argument("--delete-keyword", action="append", default=[],
                        help="Forbidden keyword (can be repeated)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only log actions, do not actually delete/ban")
    args = parser.parse_args()

    forbidden = [k.lower() for k in args.delete_keyword]
    if forbidden:
        print(f"[guard] forbidden keywords: {forbidden}")
    if args.dry_run:
        print("[guard] DRY RUN mode - no actions will be taken")

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)

    @client.on_message(peer_type="group")
    async def on_group_message(message):
        """Check each group message against the rules."""
        # Only act on the target group
        if message.peer_id != args.group_id:
            return
        if not message.text:
            return

        text_lower = message.text.lower()
        for kw in forbidden:
            if kw in text_lower:
                print(f"[guard] forbidden '{kw}' from user {message.from_id}, "
                      f"msg_id={message.id}")
                if args.dry_run:
                    print("       (dry-run) would delete message")
                else:
                    try:
                        await client.delete_message(args.group_id, message.id)
                        print("       message deleted")
                    except JetraError as e:
                        print(f"       [error] delete failed: {e}")
                return

    @client.on_ready
    def ready():
        print(f"[guard] guarding group {args.group_id} ... Ctrl+C to stop")

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
        print("\nstopped")
