# [EN] Test for multi-level Inline Keyboards and Callback Parsing.
# [FA] تست برای کیبوردهای شیشه‌ای چند سطحی و پردازش کلیک‌ها.
# How to run: python tests/test_advanced_buttons.py
# Send /menu in the bot chat.

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyjetra import JetraBot, CommandFilter, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"
bot = JetraBot(BOT_TOKEN)

@bot.on_message(filters=[CommandFilter("menu")])
def show_menu(msg):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Settings ⚙️", callback_data="settings")],
        [InlineKeyboardButton("Help ❓", callback_data="help")]
    ])
    msg.reply("Main Menu:", reply_markup=kb)

@bot.on_callback_query()
def handle_click(cb):
    if cb.data == "settings":
        cb.answer("Opening settings...")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Language 🌐", callback_data="lang")],
            [InlineKeyboardButton("Back 🔙", callback_data="back")]
        ])
        # Editing the message to show the sub-menu
        bot.edit_message_text(cb.message.chat.id, cb.message.message_id, "Settings Menu:", reply_markup=kb)
    
    elif cb.data == "back":
        cb.answer("Going back...")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Settings ⚙️", callback_data="settings")],
            [InlineKeyboardButton("Help ❓", callback_data="help")]
        ])
        bot.edit_message_text(cb.message.chat.id, cb.message.message_id, "Main Menu:", reply_markup=kb)

    elif cb.data == "help":
        cb.answer("Help is on the way!", show_alert=True)

if __name__ == "__main__":
    bot.poll()