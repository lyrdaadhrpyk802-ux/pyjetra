# ============================================
#  examples/02_bot_intermediate/03_webhook_fastapi.py - FastAPI webhook server
#  All code and comments are English. No emojis.
#
#  Prerequisites:
#    pip install fastapi uvicorn
#
#  Run:
#    export JETRA_BOT_TOKEN="your_token"
#    export JETRA_WEBHOOK_URL="https://your-domain.com/webhook"
#    export JETRA_WEBHOOK_SECRET="your_secret"
#    uvicorn examples.02_bot_intermediate.03_webhook_fastapi:app --host 0.0.0.0 --port 8000
# ============================================
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI

from pyjetra.botapi import JetraBot, CommandFilter, make_asgi_handler

TOKEN = os.getenv("JETRA_BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("JETRA_WEBHOOK_URL", "")
SECRET = os.getenv("JETRA_WEBHOOK_SECRET", "")

bot = JetraBot(TOKEN)
app = FastAPI()


@bot.on_message(filters=[CommandFilter(["start", "شروع"])])
def start(msg):
    msg.reply("ربات روی حالت webhook است.\nارسال: /ping یا /پینگ")


@bot.on_message(filters=[CommandFilter(["ping", "پینگ"])])
def ping(msg):
    msg.reply("پنگ!")


@bot.on_message(filters=[CommandFilter(["info", "اطلاعات"])])
def info(msg):
    me = bot.get_me()
    msg.reply(f"نام ربات: {me.full_name}\nشناسه: {me.id}")


@app.on_event("startup")
async def _startup():
    """Register the webhook with Jetra on startup."""
    if WEBHOOK_URL:
        bot.set_webhook(WEBHOOK_URL, secret_token=SECRET)
        print(f"webhook set to {WEBHOOK_URL}")
    else:
        print("[warn] JETRA_WEBHOOK_URL not set; server runs without registration")


@app.on_event("shutdown")
async def _shutdown():
    """Delete the webhook on shutdown."""
    if WEBHOOK_URL:
        bot.delete_webhook()
        print("webhook deleted")


# Mount the Jetra ASGI handler at /webhook
app.add_api_route(
    "/webhook",
    make_asgi_handler(bot, secret_token=SECRET),
    methods=["POST"],
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
