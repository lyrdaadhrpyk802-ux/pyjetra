# ============================================
#  jetra_fix_uid.py - temporary fix: attach the account user_id (from the old
#  session file) to the new authorized auth key, then verify with start().
#  Does not send any message. All code and comments are English. No emojis.
# ============================================
import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyjetra.userapi import JetraClient
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    with open(DEFAULT_SESSION_FILE + ".old", encoding="utf-8") as f:
        old = json.load(f)
    uid = old.get("user_id")
    print(f"[fix] user_id from old session: {uid}")
    if uid is None:
        print("[fix] old session has no user_id, stopping")
        return

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    client.session.user_id = uid
    client.session.save()
    print(f"[fix] session authorized flag: {client.session.is_authorized()}")

    await client.start()
    print("[fix] connected as authorized client, waiting 5s")
    await asyncio.sleep(5)
    await client.stop()
    print("[fix] done")


if __name__ == "__main__":
    asyncio.run(main())
