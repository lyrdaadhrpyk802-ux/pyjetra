import sys
sys.dont_write_bytecode = True
from pyjetra import JetraBot, InlineKeyboardMarkup, InlineKeyboardButton, CommandFilter, TextFilter

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"

bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("start")])
def cmd_start(message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Register", callback_data="register")],
        [InlineKeyboardButton(text="About", callback_data="about")]
    ])
    message.reply("Welcome! Use the buttons below:", reply_markup=keyboard)

@bot.on_message(filters=[TextFilter("hello")])
def say_hello(message):
    message.reply("Hello there! (Filtered text works!)")

# --- State Management (FSM) Example ---
@bot.on_message()
def handle_state(message):
    if not message.text: return
    user_id = message.from_user.id
    state = bot.get_state(user_id)

    if state == "waiting_for_name":
        bot.clear_state(user_id)
        message.reply(f"Nice to meet you, {message.text}!")
        print(f"User registered as: {message.text}")

@bot.on_callback_query()
def handle_cb(cb):
    if cb.data == "register":
        cb.answer("Starting registration...")
        bot.set_state(cb.from_user.id, "waiting_for_name")
        bot.send_message(cb.message.chat.id, "Please type your name:")
    elif cb.data == "about":
        cb.answer("This bot uses PyJetra v3.0", show_alert=True)

print("Bot is running...")
bot.poll()