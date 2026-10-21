import sys, os, asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import AsyncJetraBot, CommandFilter

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"
bot = AsyncJetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("start")])
async def start_handler(msg):
    await msg.reply("Async Bot is working at lightning speed!")
    print("Received /start in Async mode.")

if __name__ == "__main__":
    print("Starting Async Test...")
    asyncio.run(bot.start_polling())