# ============================================
#  examples/02_bot_intermediate/02_inline_buttons.py - Inline keyboard and callback queries
#  All code and comments are English. No emojis.
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import (
    JetraBot,
    CommandFilter,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
bot = JetraBot(TOKEN)


@bot.on_message(filters=[CommandFilter(["buttons", "دکمه‌ها"])])
def show_buttons(msg):
    """Show an inline keyboard with vote buttons."""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="موافق", callback_data="vote_yes"),
                InlineKeyboardButton(text="مخالف", callback_data="vote_no"),
            ],
            [InlineKeyboardButton(text="بستن", callback_data="close")],
        ]
    )
    msg.reply("آیا با قوانین موافق هستید؟", reply_markup=kb)


@bot.on_message(filters=[CommandFilter(["menu", "منو"])])
def show_menu(msg):
    """Show a navigation-style inline menu."""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="درباره ما", callback_data="nav_about"),
                InlineKeyboardButton(text="تماس", callback_data="nav_contact"),
            ],
            [InlineKeyboardButton(text="بستن منو", callback_data="close")],
        ]
    )
    msg.reply("منوی اصلی:", reply_markup=kb)


@bot.on_callback_query()
def on_callback(cb):
    """Handle all button clicks."""
    if cb.data == "vote_yes":
        cb.answer("شما موافق کردید")
        cb.message.edit("نتیجه: موافق")
    elif cb.data == "vote_no":
        cb.answer("شما مخالف کردید")
        cb.message.edit("نتیجه: مخالف")
    elif cb.data == "nav_about":
        cb.answer()
        cb.message.edit("درباره ما:\nاین یک ربات نمونه است.")
    elif cb.data == "nav_contact":
        cb.answer()
        cb.message.edit("تماس با ما:\nایمیل: example@test.com")
    elif cb.data == "close":
        cb.answer()
        cb.message.delete()


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        sys.exit(1)
    print("inline buttons bot running ... press Ctrl+C to stop")
    bot.poll()
