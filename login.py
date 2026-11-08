# ============================================
#  login.py - Login to a Jetra user account
#  All code and comments are English. No emojis.
# ============================================
import asyncio
import getpass
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError, JetraRPCError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from pyjetra.userapi.high_level import USER_CTOR


def _extract_user_id(result):
    """Try to extract (user_id, access_hash) from a TL response."""
    if not isinstance(result, (bytes, bytearray)) or len(result) < 24:
        return None, None
    needle = USER_CTOR.to_bytes(4, "little")
    pos = result.find(needle)
    if pos == -1:
        return None, None
    try:
        offset = pos + 4 + 8  # skip user ctor + 8 bytes of flags
        user_id = int.from_bytes(result[offset:offset + 8], "little", signed=True)
        offset += 8
        access_hash = int.from_bytes(result[offset:offset + 8], "little", signed=True)
        return user_id, access_hash
    except Exception:
        return None, None


async def _resolve_user_id(client, sign_result):
    """Extract user_id from the sign_in response, or fall back to get_full_user."""
    user_id, access_hash = _extract_user_id(sign_result)
    if user_id:
        return user_id, access_hash
    print("[login] could not parse sign_in response, trying get_full_user ...")
    try:
        me = await client.get_full_user()
    except JetraError as e:
        print(f"[login] get_full_user failed: {e}")
        return None, None
    if not me:
        return None, None
    return me.get("user_id"), me.get("access_hash")


async def main():
    print("=== Jetra login ===")
    print(f"[login] session_file = {DEFAULT_SESSION_FILE}")

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    try:
        await client.start(require_auth=False, timeout=30)
        print("[login] connected, DH done")
    except JetraError as e:
        print(f"[login] error: start failed: {e}")
        return 2

    try:
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
            print("[login] error: could not extract phone_code_hash")
            return 3
        print(f"[login] phone_code_hash OK (len={len(phone_code_hash)})")

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

        user_id, access_hash = await _resolve_user_id(client, sign_result)
        if not user_id:
            print("[login] error: could not determine user_id")
            if isinstance(sign_result, (bytes, bytearray)):
                print(f"[login] sign_in raw len = {len(sign_result)}")
                print(f"[login] sign_in raw hex (first 64): {sign_result[:64].hex()}")
            return 5

        client.session.user_id = user_id
        client.session.access_hash = access_hash
        client.session.save()
        print(f"[login] success: user_id = {user_id}")
        print(f"[login] session saved to {client.session.session_file}")
        return 0
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
