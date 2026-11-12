# ============================================
#  examples/06_user_advanced/04_2fa_manage.py - Set / change / remove 2FA password
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Logged in
#
#  Run:
#    python 04_2fa_manage.py set     <new_password> [hint] [email]
#    python 04_2fa_manage.py change   <old_password> <new_password> [hint]
#    python 04_2fa_manage.py remove   <current_password>
#    python 04_2fa_manage.py status
#
#  WARNING: remove_password has a known server-side limitation on Jetra
#           (returns true but does not actually remove the password).
# ============================================
import asyncio
import sys
import getpass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    if len(sys.argv) < 2:
        print("usage: python 04_2fa_manage.py <action> ...")
        print("  actions: set, change, remove, status")
        return 2

    action = sys.argv[1].lower()
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    try:
        if action == "status":
            raw = await client.get_password()
            info = client._parse_account_password(raw)
            print(f"has_password:    {info.get('has_password')}")
            print(f"has_recovery:    {info.get('has_recovery')}")
            print(f"hint:            {info.get('hint', '(none)')}")

        elif action == "set":
            if len(sys.argv) < 3:
                print("[error] usage: set <new_password> [hint] [email]")
                return 2
            new_pw = sys.argv[2]
            hint = sys.argv[3] if len(sys.argv) > 3 else ""
            email = sys.argv[4] if len(sys.argv) > 4 else None
            await client.set_password(new_pw, hint=hint, email=email)
            print(f"[ok] 2FA password set" +
                  (f" with hint '{hint}'" if hint else ""))

        elif action == "change":
            if len(sys.argv) < 4:
                print("[error] usage: change <old_password> <new_password> [hint]")
                return 2
            old_pw = sys.argv[2]
            new_pw = sys.argv[3]
            hint = sys.argv[4] if len(sys.argv) > 4 else ""
            await client.change_password(old_pw, new_pw, hint=hint)
            print("[ok] 2FA password changed")

        elif action == "remove":
            if len(sys.argv) < 3:
                print("[error] usage: remove <current_password>")
                return 2
            cur_pw = sys.argv[2]
            await client.remove_password(cur_pw)
            print("[ok] remove request sent (note: Jetra server may not actually remove it)")

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
