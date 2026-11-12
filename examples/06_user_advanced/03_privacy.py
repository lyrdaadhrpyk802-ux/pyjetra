# ============================================
#  examples/06_user_advanced/03_privacy.py - Privacy settings and birthday
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Logged in
#
#  Run:
#    python 03_privacy.py get <key>
#        key: last_seen | chat_invite | phone | photo | call | p2p | forwards | birthday
#    python 03_privacy.py set <key> <rule>
#        rule: allow_all | allow_contacts | disallow_all | allow_close_friends | allow_premium
#    python 03_privacy.py birthday <day> <month> [year]
#    python 03_privacy.py birthday clear
#    python 03_privacy.py global [--hide-read-marks] [--archive-non-contact]
# ============================================
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE

# Friendly names -> internal privacy key names
KEY_MAP = {
    "last_seen":    "status_timestamp",
    "chat_invite":  "chat_invite",
    "phone":        "phone_number",
    "photo":        "profile_photo",
    "call":         "phone_call",
    "p2p":          "phone_p2p",
    "forwards":     "forwards",
    "birthday":     "birthday",
}


async def main():
    if len(sys.argv) < 2:
        print("usage: python 03_privacy.py <action> ...")
        print("  actions: get, set, birthday, global")
        return 2

    action = sys.argv[1].lower()
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    try:
        if action == "get":
            if len(sys.argv) < 3:
                print(f"[error] key required. valid: {list(KEY_MAP.keys())}")
                return 2
            key = KEY_MAP.get(sys.argv[2])
            if not key:
                print(f"[error] unknown key. valid: {list(KEY_MAP.keys())}")
                return 2
            raw = await client.get_privacy(key)
            print(f"[ok] {sys.argv[2]} -> {len(raw)} bytes (raw TL)")

        elif action == "set":
            if len(sys.argv) < 4:
                print("[error] usage: set <key> <rule>")
                print(f"  valid keys: {list(KEY_MAP.keys())}")
                print("  valid rules: allow_all, allow_contacts, disallow_all,")
                print("               allow_close_friends, allow_premium")
                return 2
            key = KEY_MAP.get(sys.argv[2])
            if not key:
                print(f"[error] unknown key. valid: {list(KEY_MAP.keys())}")
                return 2
            rule = sys.argv[3]
            await client.set_privacy(key, [rule])
            print(f"[ok] {sys.argv[2]} set to {rule}")

        elif action == "birthday":
            if len(sys.argv) < 3:
                print("[error] usage: birthday <day> <month> [year] | birthday clear")
                return 2
            if sys.argv[2] == "clear":
                await client.update_birthday(0, 0)
                print("[ok] birthday cleared")
            else:
                if len(sys.argv) < 4:
                    print("[error] usage: birthday <day> <month> [year]")
                    return 2
                day = int(sys.argv[2])
                month = int(sys.argv[3])
                year = int(sys.argv[4]) if len(sys.argv) > 4 else 0
                await client.update_birthday(day, month, year)
                print(f"[ok] birthday set to {day}/{month}" +
                      (f"/{year}" if year else ""))

        elif action == "global":
            # Optional flags
            hide_read = "--hide-read-marks" in sys.argv
            archive = "--archive-non-contact" in sys.argv
            await client.set_global_privacy(
                archive_and_mute_new_noncontact=archive,
                hide_read_marks=hide_read,
            )
            print(f"[ok] global privacy updated (hide_read={hide_read}, archive={archive})")

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
