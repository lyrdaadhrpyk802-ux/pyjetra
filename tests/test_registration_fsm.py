# [EN] Test for State Management (FSM) - A step-by-step registration.
# [FA] تست برای مدیریت وضعیت (FSM) - یک ثبت‌نام مرحله به مرحله.
# How to run: python tests/test_registration_fsm.py
# Send /register in the bot chat.

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import JetraBot, CommandFilter

import os
BOT_TOKEN = os.environ.get("JETRA_TOKEN", "YOUR_TOKEN_HERE")
bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("register")])
def start_registration(msg):
    bot.set_state(msg.from_user.id, "waiting_for_name")
    msg.reply("Welcome! Please type your name:")

@bot.on_message()
def handle_steps(msg):
    if not msg.text or msg.text.startswith("/"):
        return

    state = bot.get_state(msg.from_user.id)
    
    if state == "waiting_for_name":
        bot.set_state(msg.from_user.id, "waiting_for_age")
        msg.reply(f"Nice to meet you, {msg.text}! How old are you?")
        
    elif state == "waiting_for_age":
        bot.clear_state(msg.from_user.id)
        msg.reply(f"You are {msg.text} years old. Registration complete! ✅")

if __name__ == "__main__":
    bot.poll()