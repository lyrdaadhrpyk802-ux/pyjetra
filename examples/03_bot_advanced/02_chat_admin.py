# ============================================
#  examples/03_bot_advanced/02_chat_admin.py - Chat admin operations
#  All code and comments are English. No emojis.
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import JetraBot, CommandFilter, ChatPermissions, JetraError

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
bot = JetraBot(TOKEN)


@bot.on_message(filters=[CommandFilter(["admins", "ادمین‌ها"])])
def list_admins(msg):
    """List chat administrators."""
    try:
        admins = bot.get_chat_administrators(msg.chat.id)
        if not admins:
            msg.reply("ادمینی یافت نشد.")
            return
        lines = [f"- {a.user.full_name} ({a.status})" for a in admins]
        msg.reply("ادمین‌های این چت:\n" + "\n".join(lines))
    except JetraError as e:
        print(f"[admins] error: {e}")
        msg.reply("خطا در دریافت لیست ادمین‌ها.")


@bot.on_message(filters=[CommandFilter(["ban", "مسدود"])])
def ban_user(msg):
    """Ban a replied-to user from the chat."""
    if not msg.reply_to_message:
        msg.reply("این دستور را روی پیام کاربر ریپلای کنید.")
        return
    target = msg.reply_to_message.from_user
    try:
        bot.ban_chat_member(msg.chat.id, target.id)
        msg.reply(f"کاربر {target.full_name} مسدود شد.")
    except JetraError as e:
        print(f"[ban] error: {e}")
        msg.reply("خطا در مسدودسازی کاربر.")


@bot.on_message(filters=[CommandFilter(["unban", "رفع"])])
def unban_user(msg):
    """Unban a user by id (passed as command argument)."""
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        msg.reply("نمونه: /unban 123456789")
        return
    try:
        uid = int(parts[1])
        bot.unban_chat_member(msg.chat.id, uid)
        msg.reply(f"کاربر {uid} رفع مسدودیت شد.")
    except ValueError:
        msg.reply("شناسه باید عدد باشد.")
    except JetraError as e:
        print(f"[unban] error: {e}")
        msg.reply("خطا در رفع مسدودیت.")


@bot.on_message(filters=[CommandFilter(["mute", "بی‌صدا"])])
def mute_user(msg):
    """Restrict a replied-to user from sending messages."""
    if not msg.reply_to_message:
        msg.reply("این دستور را روی پیام کاربر ریپلای کنید.")
        return
    target = msg.reply_to_message.from_user
    perms = ChatPermissions.muted()
    try:
        bot.restrict_chat_member(msg.chat.id, target.id, perms)
        msg.reply(f"کاربر {target.full_name} بی‌صدا شد.")
    except JetraError as e:
        print(f"[mute] error: {e}")
        msg.reply("خطا در بی‌صدا کردن کاربر.")


@bot.on_message(filters=[CommandFilter(["unmute", "بازصدا"])])
def unmute_user(msg):
    """Restore sending permissions for a replied-to user."""
    if not msg.reply_to_message:
        msg.reply("این دستور را روی پیام کاربر ریپلای کنید.")
        return
    target = msg.reply_to_message.from_user
    perms = ChatPermissions.everything()
    try:
        bot.restrict_chat_member(msg.chat.id, target.id, perms)
        msg.reply(f"کاربر {target.full_name} بازصدا شد.")
    except JetraError as e:
        print(f"[unmute] error: {e}")
        msg.reply("خطا در بازصدا کردن کاربر.")


@bot.on_message(filters=[CommandFilter(["count", "تعداد"])])
def member_count(msg):
    """Show member count of the chat."""
    try:
        n = bot.get_chat_member_count(msg.chat.id)
        msg.reply(f"تعداد اعضا: {n}")
    except JetraError as e:
        print(f"[count] error: {e}")
        msg.reply("خطا در دریافت تعداد اعضا.")


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        sys.exit(1)
    print("chat admin bot running ... press Ctrl+C to stop")
    bot.poll()
