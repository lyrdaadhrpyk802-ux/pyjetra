# ============================================
#  examples/03_bot_advanced/01_send_media.py - Send photo, document, video, audio
#  All code and comments are English. No emojis.
#
#  Usage (send a path to a local file):
#    /photo /sdcard/image.jpg
#    /document /sdcard/file.pdf
#    /video /sdcard/clip.mp4
#    /audio /sdcard/song.mp3
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import JetraBot, CommandFilter, JetraError

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
bot = JetraBot(TOKEN)


def _parse_path(msg):
    """Extract a file path from a command message. Returns None on error."""
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        msg.reply("نمونه: /photo /sdcard/image.jpg")
        return None
    path = parts[1].strip()
    if not os.path.isfile(path):
        msg.reply(f"فایل پیدا نشد: {path}")
        return None
    return path


@bot.on_message(filters=[CommandFilter(["photo", "عکس"])])
def send_photo(msg):
    """Send a photo from a local file path."""
    path = _parse_path(msg)
    if not path:
        return
    try:
        bot.send_photo(msg.chat.id, path, caption="عکس ارسال شد.")
    except JetraError as e:
        print(f"[photo] error: {e}")
        msg.reply(f"خطا در ارسال عکس: {e}")


@bot.on_message(filters=[CommandFilter(["document", "فایل"])])
def send_document(msg):
    """Send a document from a local file path."""
    path = _parse_path(msg)
    if not path:
        return
    try:
        bot.send_document(msg.chat.id, path, caption="فایل ارسال شد.")
    except JetraError as e:
        print(f"[document] error: {e}")
        msg.reply(f"خطا در ارسال فایل: {e}")


@bot.on_message(filters=[CommandFilter(["video", "ویدیو"])])
def send_video(msg):
    """Send a video from a local file path."""
    path = _parse_path(msg)
    if not path:
        return
    try:
        bot.send_video(msg.chat.id, path, caption="ویدیو ارسال شد.")
    except JetraError as e:
        print(f"[video] error: {e}")
        msg.reply(f"خطا در ارسال ویدیو: {e}")


@bot.on_message(filters=[CommandFilter(["audio", "صوت"])])
def send_audio(msg):
    """Send an audio file from a local file path."""
    path = _parse_path(msg)
    if not path:
        return
    try:
        bot.send_audio(msg.chat.id, path, caption="فایل صوتی ارسال شد.")
    except JetraError as e:
        print(f"[audio] error: {e}")
        msg.reply(f"خطا در ارسال فایل صوتی: {e}")


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        sys.exit(1)
    print("media bot running ... press Ctrl+C to stop")
    bot.poll()
