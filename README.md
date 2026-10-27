
```markdown
<div align="center">

<img src="https://raw.githubusercontent.com/lyrdaadhrpyk802-ux/pyjetra/main/logo.png" width="220" alt="PyJetra Logo">

# PyJetra

**Modern Python wrapper for the Jetra Bot API — Sync & Async**

**کتابخانه‌ی مدرن پایتون برای Jetra Bot API — همگام و ناهمگام**

[![PyPI version](https://img.shields.io/pypi/v/pyjetra?style=for-the-badge&logo=pypi&color=blue)](https://pypi.org/project/pyjetra/)
[![PyPI downloads](https://img.shields.io/pypi/dm/pyjetra?style=for-the-badge&color=purple)](https://pypi.org/project/pyjetra/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyjetra?style=for-the-badge&logo=python)](https://pypi.org/project/pyjetra/)
[![License](https://img.shields.io/github/license/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&color=orange)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&logo=github&color=yellow)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&logo=github&color=red)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/issues)
[![Jetra](https://img.shields.io/badge/jetra.ir-official-purple?style=for-the-badge)](https://jetra.ir/)

</div>

---

## About

**PyJetra** is a Python library for building [Jetra](https://jetra.ir/) bots. It wraps the **Jetra Bot API** in a clean, modern interface with full support for both synchronous and asynchronous workflows.

**PyJetra** یک کتابخانه‌ی پایتون برای ساخت ربات‌های [جترا](https://jetra.ir/) است که یک رابط تمیز و مدرن روی **Jetra Bot API** فراهم می‌کند و از هر دو حالت همگام و ناهمگام به‌طور کامل پشتیبانی می‌کند.

Whether you are building a small personal bot or a large group-management system, PyJetra gives you the tools you need — without hiding the details.

---

## Install

```bash
pip install pyjetra
```

Requires Python 3.7+. — نیازمند پایتون ۳٫۷ به بالا.

---

Features

 
🔄 Sync & Async / همگام و ناهمگام JetraBot and AsyncJetraBot with matching APIs
🎛️ Full Bot API / پوشش کامل messages, media, edits, deletes, callbacks, webhooks
🧠 FSM / مدیریت وضعیت built-in state management for multi-step flows
🎨 Inline keyboards / دکمه‌های شیشه‌ای multi-level menus, URL buttons, callbacks
🧩 Filters / فیلترها CommandFilter, TextFilter, RegexFilter
📨 Edited events / ویرایش پیام @bot.on_edited_message
📎 Full media / رسانه‌ی کامل photo, document, video, audio, voice, sticker, animation, location, contact, venue, live photo
🌐 Webhook / وب‌هوک set_webhook, delete_webhook, get_webhook_info + WSGI/ASGI handlers
💬 Rich Message / تایپ کامل replies, forwards, reply_photo, reply_document, is_forwarded, mentions
🧱 Helpers / هلپرها ChatPermissions factories, User.full_name, Chat.display_name
🛡️ Safe uploads / آپلود امن 25 MB client-side check with FileTooLargeError
🔒 Clean sessions / نشست تمیز async with AsyncJetraBot(...) for leak-free bots

---

Quick start

```python
from pyjetra import (
    JetraBot,
    CommandFilter,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

bot = JetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Open Jetra", url="https://jetra.ir")],
        [InlineKeyboardButton(text="About", callback_data="about")],
    ])
    msg.reply("Welcome to PyJetra!", reply_markup=keyboard)

@bot.on_callback_query()
def on_button(cb):
    if cb.data == "about":
        cb.answer("PyJetra - Python wrapper for the Jetra Bot API")

bot.poll()
```

---

Async

```python
import asyncio
from pyjetra import AsyncJetraBot, CommandFilter

async def main():
    async with AsyncJetraBot("YOUR_BOT_TOKEN") as bot:
        @bot.on_message(filters=[CommandFilter("start")])
        async def start(msg):
            await msg.reply("Hello from Async PyJetra!")

        await bot.start_polling()

asyncio.run(main())
```

---

Webhook (FastAPI)

```python
import os
from fastapi import FastAPI
from pyjetra import JetraBot, CommandFilter, make_asgi_handler

app = FastAPI()
bot = JetraBot(os.environ["JETRA_TOKEN"])

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    msg.reply("Hello from webhook!")

app.add_api_route(
    "/webhook",
    make_asgi_handler(bot, secret_token=os.environ["WEBHOOK_SECRET"]),
    methods=["POST"],
)

@app.on_event("startup")
def setup():
    bot.set_webhook(
        url=os.environ["WEBHOOK_URL"],
        secret_token=os.environ["WEBHOOK_SECRET"],
        allowed_updates=["message", "edited_message", "callback_query"],
    )
```

---

FSM

```python
@bot.on_message(filters=[CommandFilter("register")])
def start_register(msg):
    bot.set_state(msg.from_user.id, "waiting_for_name")
    msg.reply("What's your name? / اسمت چیه؟")

@bot.on_message()
def handle_name(msg):
    if bot.get_state(msg.from_user.id) == "waiting_for_name":
        bot.clear_state(msg.from_user.id)
        msg.reply(f"Nice to meet you, {msg.text}!")
```

---

Links

· 📦 PyPI — 
· 📁 GitHub — 
· 🐛 Issues — 
· 🚀 Releases — 
· 📖 Jetra Bot API docs — 
· 💬 PyJetra channel — 
· 👥 Community chat — 

---

Developer

<div align="center">

Ali VEX

Founder and lead developer of PyJetra
Bot developer, Python enthusiast, Jetra community member

</div>

Ali VEX created PyJetra and maintains JetraGuard, a full-featured
group-management bot built on top of it.

Platform Link
💬 Jetra profile 
📢 PyJetra channel 
👥 Community chat 
🐙 GitHub 
📧 Email 
📦 PyPI 

---

License

Released under the MIT License. See the LICENSE file for details.

---

<div align="center">

Made with ❤️ for the Jetra community — ساخته‌شده با ❤️ برای جامعه‌ی جترا

</div>
```

