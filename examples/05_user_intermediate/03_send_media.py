# ============================================
#  examples/05_user_intermediate/03_send_media.py - Upload and send media as a user
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    - Run 04_user_basics/01_login.py first.
#    - The target peer (user or group) must exist in the local dialog database.
#
#  Run:
#    python examples/05_user_intermediate/03_send_media.py <peer_id> photo /sdcard/img.jpg "caption"
#    python examples/05_user_intermediate/03_send_media.py <peer_id> document /sdcard/doc.pdf ""
#    python examples/05_user_intermediate/03_send_media.py <peer_id> video /sdcard/clip.mp4 "test"
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
    if len(sys.argv) < 4:
        print("usage: python 03_send_media.py <peer_id> <kind> <path> [caption]")
        print("  kind: photo | document | video")
        print("  path: local file path")
        print("  caption: optional text (use empty string for none)")
        return 2

    try:
        peer_id = int(sys.argv[1])
    except ValueError:
        print(f"[error] peer_id must be an integer, got: {sys.argv[1]}")
        return 2

    kind = sys.argv[2].lower()
    file_path = sys.argv[3]
    caption = sys.argv[4] if len(sys.argv) > 4 else ""

    if kind not in ("photo", "document", "video"):
        print(f"[error] kind must be photo/document/video, got: {kind}")
        return 2

    import os
    if not os.path.isfile(file_path):
        print(f"[error] file not found: {file_path}")
        return 2

    client = JetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    try:
        # send_media auto-detects file type from extension.
        # send_photo / send_document / send_video are convenience wrappers.
        if kind == "photo":
            result = await client.send_photo(peer_id, file_path, caption=caption)
        elif kind == "document":
            result = await client.send_document(peer_id, file_path, caption=caption)
        else:
            result = await client.send_video(peer_id, file_path, caption=caption)

        # result is a parsed dict (msg_id, date) or {"raw_len": N}
        if isinstance(result, dict):
            msg_id = result.get("msg_id")
            if msg_id:
                print(f"[ok] {kind} sent, msg_id={msg_id}")
            else:
                print(f"[ok] {kind} sent (raw response, len={result.get('raw_len', 0)})")
        else:
            print(f"[ok] {kind} sent")
        return 0
    except JetraError as e:
        print(f"[error] send_{kind} failed: {e}")
        return 1
    finally:
        await client.stop()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
