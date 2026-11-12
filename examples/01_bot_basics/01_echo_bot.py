# ============================================
#  examples/01_bot_basics/01_echo_bot.py
#  Echo bot with Persian and English commands.
#  All code and comments are English. No emojis.
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import JetraBot, CommandFilter

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")

bot = JetraBot(TOKEN)


@bot.on_message(filters=[CommandFilter(["start", "شروع"])])
def start(msg):
    """Greet the user when they start the bot."""
    msg.reply("سلام! من یک ربات نمونه هستم.")
    msg.reply("برای راهنما /help یا /راهنما را بفرست.")


@bot.on_message(filters=[CommandFilter(["help", "راهنما"])])
def help_cmd(msg):
    """List available commands."""
    text = (
        "راهنما:\n"
        "/start یا /شروع - شروع کار\n"
        "/help یا /راهنما - همین پیام\n"
        "/echo یا /تکرار <متن> - تکرار متن شما\n"
        "/about یا /درباره - اطلاعات ربات"
    )
    msg.reply(text)


@bot.on_message(filters=[CommandFilter(["echo", "تکرار"])])
def echo_cmd(msg):
    """Repeat the text that follows the command."""
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        msg.reply("نمونه: /echo سلام دنیا")
        return
    msg.reply(parts[1])


@bot.on_message(filters=[CommandFilter(["about", "درباره"])])
def about_cmd(msg):
    """Show bot identity."""
    me = bot.get_me()
    msg.reply("نام: {0}\nشناسه: {1}\nیوزرنیم: @{2}".format(
        me.full_name, me.id, me.username
    ))


@bot.on_message()
def fallback(msg):
    """Echo any non-command text back to the sender."""
    if not msg.text:
        return
    if msg.text.startswith("/"):
        return
    msg.reply(msg.text)


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        print("        export JETRA_BOT_TOKEN='your_token_here'")
        sys.exit(1)
    print("echo bot running ... press Ctrl+C to stop")
    bot.poll()
