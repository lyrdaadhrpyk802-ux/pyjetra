# ============================================
#  examples/05_user_intermediate/02_get_participants.py - List group participants
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Run 04_user_basics/01_login.py first.
#    - The bot/user must be a member of the target group.
#
#  Run:
#    python examples/05_user_intermediate/02_get_participants.py <group_id>
#    python examples/05_user_intermediate/02_get_participants.py <group_id> --full
#    python examples/05_user_intermediate/02_get_participants.py <group_id> --filter bots
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
    parser = argparse.ArgumentParser(description="List group participants")
    parser.add_argument("group_id", type=int, help="Group/channel id")
    parser.add_argument(
        "--full", action="store_true",
        help="Show access_hash too (needed for ban/kick)"
    )
    parser.add_argument(
        "--filter", default="recent",
        choices=["recent", "admin", "kicked", "banned", "bots",
                 "contacts", "non_contacts", "mentions", "search"],
        help="Filter type (default: recent)"
    )
    parser.add_argument(
        "--query", default="",
        help="Search query (only used with --filter search)"
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Max participants to fetch (default: 100)"
    )
    args = parser.parse_args()

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        if args.filter == "recent" and not args.full:
            # Simple path: list of user_ids only
            user_ids = await client.get_participants(args.group_id)
            print(f"--- {len(user_ids)} participants ---")
            for uid in user_ids[:args.limit]:
                print(f"  user_id: {uid}")
        else:
            # Filtered path: raw bytes from the server (parse manually if needed)
            raw = await client.get_participants_filtered(
                args.group_id,
                filter_type=args.filter,
                query=args.query,
                limit=args.limit,
            )
            print(f"--- raw response, {len(raw)} bytes ---")
            print(f"(filter={args.filter}, group_id={args.group_id})")
            print("note: filtered responses are raw TL bytes;")
            print("      use _extract_users helper to parse them.")
        return 0
    except JetraError as e:
        print(f"[error] get_participants failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
