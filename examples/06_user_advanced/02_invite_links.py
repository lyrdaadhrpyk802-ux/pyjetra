# ============================================
#  examples/06_user_advanced/02_invite_links.py - Chat invite link management
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Logged in
#    - You must have invite permission in the target chat
#
#  Run:
#    python 02_invite_links.py create <group_id> [--title "name"] [--uses 10] [--expire 86400]
#    python 02_invite_links.py list   <group_id>
#    python 02_invite_links.py revoke <group_id> <link_url>
#    python 02_invite_links.py delete <group_id> <link_url>
#    python 02_invite_links.py import <invite_hash>
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
    if len(sys.argv) < 2:
        print("usage: python 02_invite_links.py <action> ...")
        print("  actions: create, list, revoke, delete, import")
        return 2

    action = sys.argv[1].lower()
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    try:
        if action == "create":
            parser = argparse.ArgumentParser(prog="invite create")
            parser.add_argument("group_id", type=int)
            parser.add_argument("--title", default="")
            parser.add_argument("--uses", type=int, default=0,
                                help="Max uses (0 = unlimited)")
            parser.add_argument("--expire", type=int, default=0,
                                help="Expire after N seconds (0 = never)")
            parser.add_argument("--request", action="store_true",
                                help="Require admin approval")
            args = parser.parse_args(sys.argv[2:])

            raw = await client.export_chat_invite(
                args.group_id,
                title=args.title,
                expire_date=args.expire,
                usage_limit=args.uses,
                request_needed=args.request,
            )
            link = client._extract_invite_link(raw) or "(unknown)"
            print(f"[ok] invite created: {link}")

        elif action == "list":
            if len(sys.argv) < 3:
                print("[error] group_id required")
                return 2
            gid = int(sys.argv[2])
            raw = await client.get_chat_invites(gid)
            print(f"[ok] raw response, {len(raw)} bytes")
            print("(parse raw bytes to enumerate links;)")

        elif action == "revoke":
            if len(sys.argv) < 4:
                print("[error] usage: revoke <group_id> <link_url>")
                return 2
            gid = int(sys.argv[2])
            link = sys.argv[3]
            await client.edit_chat_invite(gid, link, revoked=True)
            print(f"[ok] link revoked: {link}")

        elif action == "delete":
            if len(sys.argv) < 4:
                print("[error] usage: delete <group_id> <link_url>")
                return 2
            gid = int(sys.argv[2])
            link = sys.argv[3]
            await client.delete_chat_invite(gid, link)
            print(f"[ok] link deleted: {link}")

        elif action == "import":
            if len(sys.argv) < 3:
                print("[error] invite_hash required")
                return 2
            invite_hash = sys.argv[2]
            await client.import_chat_invite(invite_hash)
            print(f"[ok] joined via invite")

        else:
            print(f"[error] unknown action: {action}")
            return 2

        return 0
    except JetraError as e:
        print(f"[error] {action} failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
