import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import JetraBot, CommandFilter

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"
bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("start")])
def start_handler(msg):
    msg.reply("Sync Bot is working perfectly!")
    print("Received /start in Sync mode.")

if __name__ == "__main__":
    print("Starting Sync Test...")
    bot.poll()