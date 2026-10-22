# [EN] Test how the library handles API errors gracefully.
# [FA] تست اینکه کتابخانه چگونه خطاهای API را مدیریت می‌کند.
# How to run: python tests/test_error_handling.py
# Send /error in the bot chat.

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import JetraBot, CommandFilter, JetraError

import os
BOT_TOKEN = os.environ.get("JETRA_TOKEN", "YOUR_TOKEN_HERE")
bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("error")])
def trigger_error(msg):
    try:
        # Trying to send a message to an invalid Chat ID (999999999)
        bot.send_message(999999999, "This will fail!")
    except JetraError as e:
        # Catch the error and inform the user
        msg.reply(f"Successfully caught an error: {e}")
        print(f"Error logged: {e}")

if __name__ == "__main__":
    bot.poll()