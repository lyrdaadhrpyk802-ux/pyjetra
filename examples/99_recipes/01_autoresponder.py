# ============================================
#  examples/99_recipes/01_autoresponder.py - Bot API autoresponder with keywords
#  All code and comments are English. No emojis.
#
#  Replies automatically based on keyword matching. Supports Persian and English
#  keywords. Useful for support bots, FAQs, and simple info bots.
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import JetraBot, CommandFilter, KeywordFilter

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
bot = JetraBot(TOKEN)

# Keyword -> reply mapping (case-insensitive, first-word match)
REPLIES = {
    # Persian keywords
    "سلام":       "سلام! چطور می‌تونم کمکتون کنم؟ برای راهنما /help یا /راهنما بفرستید.",
    "خداحافظ":    "خداحافظ! برگردید منتظرتون هستیم.",
    "قیمت":       "برای دریافت قیمت‌ها از /price یا /قیمت استفاده کنید.",
    "پشتیبانی":   "با پشتیبانی در ارتباط هستید. مشکل خود را بنویسید.",
    "ساعات":      "ساعات کاری: شنبه تا چهارشنبه ۹ تا ۱۸.",
    "آدرس":       "آدرس: تهران، خیابان ولیعصر، پلاک ۱۲۳.",

    # English keywords
    "hello":      "Hello! How can I help you? Send /help for the menu.",
    "bye":        "Goodbye! Come back soon.",
    "price":      "Use /price or /قیمت to get our price list.",
    "support":    "You are now talking to support. Please describe your issue.",
    "hours":      "Working hours: Sat-Wed, 9am to 6pm.",
    "address":    "Address: 123 Vali-asr St, Tehran.",
}


@bot.on_message(filters=[CommandFilter(["start", "شروع"])])
def start(msg):
    msg.reply(
        "ربات پاسخگوی خودکار\n"
        "کلمات کلیدی پشتیبانی شده:\n"
        "  سلام، خداحافظ، قیمت، پشتیبانی، ساعات، آدرس\n"
        "  hello, bye, price, support, hours, address\n"
        "\nبرای راهنما: /help یا /راهنما"
    )


@bot.on_message(filters=[CommandFilter(["help", "راهنما"])])
def help_cmd(msg):
    msg.reply(
        "راهنما:\n"
        "- یکی از کلمات کلیدی بالا را بفرستید.\n"
        "- هر کلمه‌ی ناشناخته به پشتیبانی انسانی ارجاع داده می‌شود.\n"
        "- /start یا /شروع - شروع کار\n"
        "- /help یا /راهنما - همین پیام"
    )


@bot.on_message(filters=[CommandFilter(["price", "قیمت"])])
def price_cmd(msg):
    msg.reply(
        "لیست قیمت:\n"
        "  محصول A: ۱۰۰٬۰۰۰ تومان\n"
        "  محصول B: ۲۵۰٬۰۰۰ تومان\n"
        "  محصول C: ۵۰۰٬۰۰۰ تومان"
    )


# Register a handler for each keyword
for kw, reply in REPLIES.items():
    def _make_handler(reply_text):
        def handler(msg):
            msg.reply(reply_text)
        return handler
    bot.on_message(filters=[KeywordFilter(kw)])(_make_handler(reply))


@bot.on_message()
def fallback(msg):
    """Catch-all: forward unknown messages to support."""
    if msg.is_command:
        return
    if not msg.text:
        return
    # Acknowledge that the message will be handled by a human
    msg.reply(
        "پیام شما دریافت شد.\n"
        "یکی از پشتیبانی‌ها به زودی پاسخ می‌دهد.\n"
        "برای راهنما: /help"
    )


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        sys.exit(1)
    print("autoresponder bot running ... press Ctrl+C to stop")
    bot.poll()
