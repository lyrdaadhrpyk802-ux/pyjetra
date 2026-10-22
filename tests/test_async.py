import sys, os, asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import AsyncJetraBot, CommandFilter

import os
BOT_TOKEN = os.environ.get("JETRA_TOKEN", "YOUR_TOKEN_HERE")
bot = AsyncJetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("start")])
async def start_handler(msg):
    await msg.reply("Async Bot is working at lightning speed!")
    print("Received /start in Async mode.")

if __name__ == "__main__":
    print("Starting Async Test...")
    asyncio.run(bot.start_polling())