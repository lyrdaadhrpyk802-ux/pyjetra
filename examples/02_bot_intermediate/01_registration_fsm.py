# ============================================
#  examples/02_bot_intermediate/01_registration_fsm.py - Multi-step registration using FSM
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

# FSM states
STATE_AWAIT_NAME = "await_name"
STATE_AWAIT_AGE = "await_age"
STATE_AWAIT_EMAIL = "await_email"

# In-memory store for registration data (lost on restart)
_reg_data = {}


@bot.on_message(filters=[CommandFilter(["register", "ثبت‌نام"])])
def register_start(msg):
    """Begin the registration flow."""
    bot.set_state(msg.from_user.id, STATE_AWAIT_NAME)
    _reg_data[msg.from_user.id] = {}
    msg.reply("ثبت‌نام شروع شد.\nنام خود را وارد کنید:")


@bot.on_message(filters=[CommandFilter(["cancel", "لغو"])])
def cancel(msg):
    """Cancel an in-progress registration."""
    bot.clear_state(msg.from_user.id)
    _reg_data.pop(msg.from_user.id, None)
    msg.reply("عملیات لغو شد.")


@bot.on_message()
def handle(msg):
    """Dispatch based on the user's current state."""
    if msg.is_command:
        return
    if not msg.text:
        return

    uid = msg.from_user.id
    state = bot.get_state(uid)

    if state == STATE_AWAIT_NAME:
        _reg_data[uid]["name"] = msg.text
        bot.set_state(uid, STATE_AWAIT_AGE)
        msg.reply("سن خود را وارد کنید (فقط عدد):")

    elif state == STATE_AWAIT_AGE:
        if not msg.text.isdigit():
            msg.reply("لطفاً یک عدد معتبر وارد کنید.")
            return
        _reg_data[uid]["age"] = int(msg.text)
        bot.set_state(uid, STATE_AWAIT_EMAIL)
        msg.reply("ایمیل خود را وارد کنید:")

    elif state == STATE_AWAIT_EMAIL:
        _reg_data[uid]["email"] = msg.text
        bot.clear_state(uid)
        data = _reg_data.pop(uid, {})
        msg.reply(
            f"ثبت‌نام کامل شد!\n"
            f"نام: {data.get('name', '?')}\n"
            f"سن: {data.get('age', '?')}\n"
            f"ایمیل: {data.get('email', '?')}"
        )


if __name__ == "__main__":
    if not TOKEN:
        print("[error] set JETRA_BOT_TOKEN env var first")
        print("        export JETRA_BOT_TOKEN='your_token_here'")
        sys.exit(1)
    print("registration bot running ... press Ctrl+C to stop")
    bot.poll()
