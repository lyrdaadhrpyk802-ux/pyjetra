# ============================================
#  examples/04_user_basics/01_login.py - Interactive login flow (phone -> code -> 2FA)
#  All code and comments are English. No emojis.
#
#  Run:
#    python examples/04_user_basics/01_login.py
#
#  After success, session is saved to ~/.pyjetra/jetra_session.json
# ============================================
import asyncio
import getpass
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError, JetraRPCError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    print("=== Jetra user login ===")
    print(f"[login] session file: {DEFAULT_SESSION_FILE}")

    # require_auth=False so we can run the DH handshake without an existing session.
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    try:
        await client.start(require_auth=False, timeout=30)
        print("[login] connected, DH handshake done")
    except JetraError as e:
        print(f"[login] error: start failed: {e}")
        return 2

    try:
        # Already authorized? Skip login.
        if client.session.is_authorized():
            print(f"[login] already authorized as user_id={client.session.user_id}")
            return 0

        # Step 1: send SMS code
        phone = input("Phone (+98...): ").strip()
        if not phone:
            print("[login] error: empty phone")
            return 2
        if not phone.startswith("+"):
            phone = "+" + phone

        print("[login] sending code ...")
        code_info = await client.send_code(phone)
        phone_code_hash = code_info.get("phone_code_hash")
        if not phone_code_hash:
            print(f"[login] error: no phone_code_hash in response: {code_info}")
            return 3
        print(f"[login] phone_code_hash OK (len={len(phone_code_hash)})")

        # Step 2: sign in with the code
        code = input("SMS code: ").strip()
        if not code:
            print("[login] error: empty code")
            return 2

        print("[login] signing in ...")
        try:
            sign_result = await client.sign_in(phone, phone_code_hash, code)
        except JetraRPCError as e:
            msg = str(e)
            if "SESSION_PASSWORD_NEEDED" in msg:
                # Step 3: 2FA password (SRP)
                print("[login] 2FA required")
                password = getpass.getpass("2FA password: ")
                try:
                    sign_result = await client.check_password(password)
                except JetraError as e2:
                    print(f"[login] error: check_password failed: {e2}")
                    return 4
            else:
                print(f"[login] error: sign_in failed: {msg}")
                return 4

        # Try to extract user_id from the sign_in response.
        user_id = None
        if isinstance(sign_result, dict):
            user_id = sign_result.get("user_id")
        if not user_id:
            # Fallback: query own profile.
            try:
                me = await client.get_full_user()
                if me:
                    user_id = me.get("user_id")
            except JetraError as e:
                print(f"[login] get_full_user failed: {e}")

        if not user_id:
            print("[login] error: could not determine user_id")
            return 5

        client.session.user_id = user_id
        client.session.save()
        print(f"[login] success: user_id = {user_id}")
        print(f"[login] session saved to {client.session.session_file}")
        return 0
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
