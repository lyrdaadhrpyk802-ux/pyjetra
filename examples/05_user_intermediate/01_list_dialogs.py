# ============================================
#  examples/05_user_intermediate/01_list_dialogs.py - List dialogs from local DB
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Run 04_user_basics/01_login.py first.
#
#  Run:
#    python examples/05_user_intermediate/01_list_dialogs.py
#    python examples/05_user_intermediate/01_list_dialogs.py --type user
#    python examples/05_user_intermediate/01_list_dialogs.py --type group
# ============================================
import asyncio
import sys
import argparse
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    parser = argparse.ArgumentParser(description="List Jetra dialogs")
    parser.add_argument(
        "--type", choices=["user", "group"], default=None,
        help="Filter by peer type (default: all)"
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max dialogs to show (default: 50)"
    )
    args = parser.parse_args()

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        dialogs = await client.get_dialogs(peer_type=args.type)
        if not dialogs:
            print("[info] no dialogs found")
            print("       if you just logged in, run this script again")
            print("       (dialogs are loaded on start and cached locally)")
            return 0

        # Sort by title for readability
        dialogs.sort(key=lambda d: (d.get("peer_type", ""), d.get("title") or ""))

        shown = dialogs[:args.limit]
        print(f"--- {len(shown)} of {len(dialogs)} dialogs ---")
        for d in shown:
            pid = d.get("peer_id")
            ptype = d.get("peer_type", "?")
            title = d.get("title") or "(no title)"
            print(f"  [{ptype:5}] {pid:>14}  {title}")
        return 0
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
