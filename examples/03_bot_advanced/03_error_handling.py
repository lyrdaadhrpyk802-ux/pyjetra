# ============================================
#  examples/03_bot_advanced/03_error_handling.py - Error handling patterns
#  All code and comments are English. No emojis.
# ============================================
import os
import sys
import time
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pyjetra.botapi import JetraBot, CommandFilter, JetraError

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
bot = JetraBot(TOKEN)


def safe_call(msg, fn, *args, **kwargs):
    """Call a bot API method with retry and error handling.

    Args:
        msg: Message object (for sending error replies to the user).
        fn:  Bot method to call.
        *args, **kwargs: Arguments passed to the method.

    Returns:
        The method result on success, None on failure.
    """
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except JetraError as e:
            print(f"[safe_call] attempt {attempt}/{max_attempts} JetraError: {e}")
            if attempt == max_attempts:
                msg.reply(f"خطا پس از {max_attempts} تلاش:\n{e}")
                return None
            time.sleep(1 * attempt)
        except Exception as e:
            print(f"[safe_call] unexpected error: {e}")
            traceback.print_exc()
            msg.reply("خطای غیرمنتظره رخ داد. لاگ را ببینید.")
            return None


@bot.on_message(filters=[CommandFilter(["safe", "امن"])])
def safe_send(msg):
    """Send a message using the safe_call wrapper."""
    safe_call(
        msg,
        bot.send_message,
        msg.chat.id,
        "این پیام از طریق safe_call ارسال شد.",
    )


@bot.on_message(filters=[CommandFilter(["fail", "شکست"])])
def trigger_fail(msg):
    """Trigger an intentional error to demonstrate error handling."""
    # An invalid chat_id will cause the server to return an error.
    safe_call(msg, bot.get_chat, 0)


@bot.on_message(filters=[CommandFilter(["retry", "تلاش"])])
def retry_demo(msg):
    """Demonstrate retry logic with a normal send."""
    result = safe_call(
        msg, bot.send_message, msg.chat.id, "پیام با تلاش مجدد ارسال شد."
    )
    if result:
        msg.reply("موفقیت آمیز بود.")


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        sys.exit(1)
    print("error handling bot running ... press Ctrl+C to stop")
    bot.poll()
