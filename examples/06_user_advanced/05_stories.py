# ============================================
#  examples/06_user_advanced/05_stories.py - Send and fetch stories
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Logged in
#    - For send: peer must allow you to post stories (usually yourself)
#
#  Run:
#    python 05_stories.py send   <peer_id> <photo_path> [caption]
#    python 05_stories.py list    <peer_id>
#    python 05_stories.py all
#    python 05_stories.py delete  <peer_id> <story_id1> [story_id2 ...]
# ============================================
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.userapi import JetraClient, JetraError
from pyjetra.userapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE


async def main():
    if len(sys.argv) < 2:
        print("usage: python 05_stories.py <action> ...")
        print("  actions: send, list, all, delete")
        return 2

    action = sys.argv[1].lower()
    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    try:
        if action == "send":
            if len(sys.argv) < 4:
                print("[error] usage: send <peer_id> <photo_path> [caption]")
                return 2
            import os
            peer_id = int(sys.argv[2])
            photo_path = sys.argv[3]
            caption = sys.argv[4] if len(sys.argv) > 4 else ""
            if not os.path.isfile(photo_path):
                print(f"[error] file not found: {photo_path}")
                return 2
            await client.send_story(peer_id, photo_path, caption=caption)
            print(f"[ok] story sent to peer {peer_id}")

        elif action == "list":
            if len(sys.argv) < 3:
                print("[error] usage: list <peer_id>")
                return 2
            peer_id = int(sys.argv[2])
            raw = await client.get_peer_stories(peer_id)
            print(f"[ok] raw response, {len(raw)} bytes")

        elif action == "all":
            raw = await client.get_all_stories()
            print(f"[ok] raw response, {len(raw)} bytes")

        elif action == "delete":
            if len(sys.argv) < 4:
                print("[error] usage: delete <peer_id> <story_id> [story_id ...]")
                return 2
            peer_id = int(sys.argv[2])
            story_ids = [int(x) for x in sys.argv[3:]]
            await client.delete_stories(peer_id, story_ids)
            print(f"[ok] {len(story_ids)} stories deleted from peer {peer_id}")

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
