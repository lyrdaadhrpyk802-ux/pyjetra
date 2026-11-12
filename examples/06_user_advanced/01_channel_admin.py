# ============================================
#  examples/06_user_advanced/01_channel_admin.py - Channel admin operations
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Logged in (run 04_user_basics/01_login.py first)
#    - You must be admin in the target channel/group
#
#  Run:
#    python 01_channel_admin.py title <group_id> "عنوان جدید"
#    python 01_channel_admin.py photo <group_id> /sdcard/photo.jpg
#    python 01_channel_admin.py promote <group_id> <user_id>
#    python 01_channel_admin.py demote <group_id> <user_id>
#    python 01_channel_admin.py ban <group_id> <user_id>
#    python 01_channel_admin.py unban <group_id> <user_id>
#    python 01_channel_admin.py leave <group_id>
# ============================================
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

USAGE = """usage:
  python 01_channel_admin.py title   <group_id> "<new_title>"
  python 01_channel_admin.py photo   <group_id> <photo_path>
  python 01_channel_admin.py promote <group_id> <user_id>
  python 01_channel_admin.py demote  <group_id> <user_id>
  python 01_channel_admin.py ban     <group_id> <user_id>
  python 01_channel_admin.py unban   <group_id> <user_id>
  python 01_channel_admin.py leave    <group_id>
"""


async def main():
    if len(sys.argv) < 3:
        print(USAGE)
        return 2

    action = sys.argv[1].lower()
    try:
        group_id = int(sys.argv[2])
    except ValueError:
        print(f"[error] group_id must be an integer, got: {sys.argv[2]}")
        return 2

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        if action == "title":
            if len(sys.argv) < 4:
                print("[error] title required")
                return 2
            await client.edit_chat_title(group_id, sys.argv[3])
            print(f"[ok] title changed to: {sys.argv[3]}")

        elif action == "photo":
            if len(sys.argv) < 4:
                print("[error] photo_path required")
                return 2
            import os
            if not os.path.isfile(sys.argv[3]):
                print(f"[error] file not found: {sys.argv[3]}")
                return 2
            await client.edit_chat_photo(group_id, sys.argv[3])
            print("[ok] photo updated")

        elif action == "promote":
            if len(sys.argv) < 4:
                print("[error] user_id required")
                return 2
            uid = int(sys.argv[3])
            # Default admin rights: ban_users, invite_users, pin_messages
            await client.promote_admin(group_id, uid, rights={
                "ban_users": True,
                "invite_users": True,
                "pin_messages": True,
            })
            print(f"[ok] user {uid} promoted to admin")

        elif action == "demote":
            if len(sys.argv) < 4:
                print("[error] user_id required")
                return 2
            uid = int(sys.argv[3])
            await client.demote_admin(group_id, uid)
            print(f"[ok] user {uid} demoted to regular member")

        elif action == "ban":
            if len(sys.argv) < 4:
                print("[error] user_id required")
                return 2
            uid = int(sys.argv[3])
            await client.ban_user(group_id, uid)
            print(f"[ok] user {uid} banned")

        elif action == "unban":
            if len(sys.argv) < 4:
                print("[error] user_id required")
                return 2
            uid = int(sys.argv[3])
            await client.unban_user(group_id, uid)
            print(f"[ok] user {uid} unbanned")

        elif action == "leave":
            await client.leave_channel(group_id)
            print(f"[ok] left channel {group_id}")

        else:
            print(f"[error] unknown action: {action}")
            print(USAGE)
            return 2

        return 0
    except JetraError as e:
        print(f"[error] {action} failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
