# ============================================
#  jetra_login.py - full Jetra login: phone, OTP, and optional 2FA password.
#  Secrets are typed locally (password is hidden) and never printed.
#  All code and comments are English. No emojis.
# ============================================
import sys
import asyncio
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyjetra.userapi import JetraClient, JetraRPCError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start(require_auth=False)
    try:
        if client.session.is_authorized():
            print("[login] session is already authorized")
            return

        phone = input("Phone number (e.g. +989123456789): ").strip()
        sent = await client.send_code(phone)
        code_hash = sent.get("phone_code_hash")
        if not code_hash:
            print(f"[login] no phone_code_hash in response: {sent}")
            return

        code = input("Code: ").strip()
        try:
            res = await client.sign_in(phone, code_hash, code)
            print(f"[login] signed in: user_id={res.get('user_id')}")
        except JetraRPCError as e:
            if "SESSION_PASSWORD_NEEDED" not in str(e):
                print(f"[login] sign_in failed: {e}")
                return
            print("[login] two-step verification is enabled")
            password = getpass.getpass("2FA password (hidden): ")
            try:
                res = await client.check_password(password)
                print("[login] signed in with 2FA password")
            except JetraRPCError as e2:
                print(f"[login] check_password failed: {e2}")
                return
        print(f"[login] authorized: {client.session.is_authorized()}")
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
