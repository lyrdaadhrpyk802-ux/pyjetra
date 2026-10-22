import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import JetraBot, CommandFilter

import os
BOT_TOKEN = os.environ.get("JETRA_TOKEN", "YOUR_TOKEN_HERE")
bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("start")])
def start_handler(msg):
    msg.reply("Sync Bot is working perfectly!")
    print("Received /start in Sync mode.")

if __name__ == "__main__":
    print("Starting Sync Test...")
    bot.poll()