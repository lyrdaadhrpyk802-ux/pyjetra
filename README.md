```markdown
<div align="center">

<img src="https://raw.githubusercontent.com/lyrdaadhrpyk802-ux/pyjetra/main/logo.png" width="220" alt="PyJetra Logo">

# PyJetra

**A modern, bilingual (Sync & Async) Python wrapper for the Jetra Bot API**

[![PyPI version](https://img.shields.io/pypi/v/pyjetra?style=for-the-badge&logo=pypi&color=blue)](https://pypi.org/project/pyjetra/)
[![PyPI downloads](https://img.shields.io/pypi/dm/pyjetra?style=for-the-badge&color=purple)](https://pypi.org/project/pyjetra/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyjetra?style=for-the-badge&logo=python)](https://pypi.org/project/pyjetra/)
[![License](https://img.shields.io/github/license/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&color=orange)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&logo=github&color=yellow)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&logo=github&color=red)](https://github.com/lyrdaadhrpyk802-ux/pyjetra/issues)
[![Jetra](https://img.shields.io/badge/jetra.ir-official-purple?style=for-the-badge)](https://jetra.ir/)

<a href="https://pypi.org/project/pyjetra/">
  <img src="https://img.shields.io/badge/install-pip%20install%20pyjetra-blue?style=for-the-badge" alt="Install">
</a>
<a href="https://github.com/lyrdaadhrpyk802-ux/pyjetra">
  <img src="https://img.shields.io/badge/source-github-black?style=for-the-badge&logo=github" alt="Source">
</a>
<a href="https://jetra.ir/docs/bots">
  <img src="https://img.shields.io/badge/docs-jetra.ir-blueviolet?style=for-the-badge" alt="Docs">
</a>

</div>

---

## English

### What is PyJetra?

**PyJetra** is a Python library for building [Jetra](https://jetra.ir/) bots.
It wraps the **Jetra Bot API** in a clean, modern interface with full support
for both **synchronous** and **asynchronous** workflows.

Whether you are building a small personal bot or a large group-management
system, PyJetra gives you the tools you need without hiding the details.

### Highlights

| | |
|---|---|
| 🔄 **Sync & Async** | `JetraBot` and `AsyncJetraBot` with matching APIs |
| 🎛️ **Full Bot API** | messages, media, edits, deletes, callbacks, webhooks |
| 🧠 **FSM** | built-in state management for multi-step conversations |
| 🎨 **Inline keyboards** | multi-level menus, URL buttons, callback handlers |
| 🧩 **Filters** | `CommandFilter`, `TextFilter`, `RegexFilter` |
| 📨 **Edited events** | `@bot.on_edited_message` |
| 📎 **Full media** | photo, document, video, audio, voice, sticker, animation, location, contact, venue, live photo |
| 🌐 **Webhook ready** | `set_webhook`, `delete_webhook`, `get_webhook_info` + ready-to-use WSGI/ASGI handlers |
| 💬 **Rich `Message`** | replies, forwards, service events, `reply_photo`, `reply_document`, `is_forwarded`, `mentions` |
| 🧱 **Helpers** | `ChatPermissions` factories, `User.full_name`, `Chat.display_name` |
| 🐍 **Pythonic** | type hints, clean dataclasses, no boilerplate |
| 🛡️ **Safe uploads** | 25 MB client-side check with `FileTooLargeError` |
| 🔒 **Clean sessions** | `async with AsyncJetraBot(...)` for leak-free async bots |

### Installation

```bash
pip install pyjetra
```

Requires Python 3.7+.

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

Async example

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

Webhook example (FastAPI)

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

FSM example

```python
@bot.on_message(filters=[CommandFilter("register")])
def start_register(msg):
    bot.set_state(msg.from_user.id, "waiting_for_name")
    msg.reply("What's your name?")

@bot.on_message()
def handle_name(msg):
    if bot.get_state(msg.from_user.id) == "waiting_for_name":
        bot.clear_state(msg.from_user.id)
        msg.reply(f"Nice to meet you, {msg.full_name if hasattr(msg, 'full_name') else msg.text}!")
```

Links

· 📦 PyPI: 
· 📁 GitHub: 
· 🐛 Issues: 
· 🚀 Releases: 
· 📖 Jetra Bot API docs: 
· 💬 PyJetra channel: 
· 👥 Community chat: 

---

فارسی

PyJetra چیست؟

PyJetra یک کتابخانه‌ی پایتون برای ساخت ربات‌های
جترا است. این کتابخانه یک رابط تمیز و مدرن روی
Jetra Bot API فراهم می‌کند و از هر دو حالت همگام (Sync) و
ناهمگام (Async) به‌طور کامل پشتیبانی می‌کند.

چه یک ربات شخصی کوچک بسازید و چه یک سیستم مدیریت گروه بزرگ،
PyJetra تمام ابزارهای لازم را در اختیار شما قرار می‌دهد.

امکانات

 
🔄 همگام و ناهمگام JetraBot و AsyncJetraBot با API یکسان
🎛️ پوشش کامل Bot API پیام، رسانه، ویرایش، حذف، کال‌بک، وب‌هوک
🧠 مدیریت وضعیت (FSM) برای گفتگوهای چندمرحله‌ای
🎨 دکمه‌های شیشه‌ای منوهای چندسطحی، دکمه‌های لینک، کال‌بک
🧩 فیلترها CommandFilter، TextFilter، RegexFilter
📨 رویداد ویرایش پیام @bot.on_edited_message
📎 پشتیبانی کامل رسانه عکس، فایل، ویدیو، صدا، ویس، استیکر، انیمیشن، موقعیت، مخاطب، مکان، لایو فوتو
🌐 آماده‌ی وب‌هوک set_webhook، delete_webhook، get_webhook_info + هندلر آماده‌ی WSGI/ASGI
💬 تایپ کامل Message پاسخ‌ها، فوروارد، رویدادهای سرویس، reply_photo، reply_document، is_forwarded، mentions
🧱 هلپرها ChatPermissions factories، User.full_name، Chat.display_name
🐍 پایتونیک type hint، dataclass تمیز، بدون کد اضافه
🛡️ آپلود امن چک ۲۵ مگابایت سمت کلاینت با FileTooLargeError
🔒 نشست‌های تمیز async with AsyncJetraBot(...) برای ربات‌های async بدون نشتی

نصب

```bash
pip install pyjetra
```

نیازمند پایتون ۳٫۷ به بالا.

شروع سریع

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
        [InlineKeyboardButton(text="ورود به جترا", url="https://jetra.ir")],
        [InlineKeyboardButton(text="درباره", callback_data="about")],
    ])
    msg.reply("به PyJetra خوش آمدید!", reply_markup=keyboard)

@bot.on_callback_query()
def on_button(cb):
    if cb.data == "about":
        cb.answer("PyJetra - کتابخانه‌ی پایتون برای Jetra Bot API")

bot.poll()
```

مثال async

```python
import asyncio
from pyjetra import AsyncJetraBot, CommandFilter

async def main():
    async with AsyncJetraBot("YOUR_BOT_TOKEN") as bot:
        @bot.on_message(filters=[CommandFilter("start")])
        async def start(msg):
            await msg.reply("سلام از Async PyJetra!")

        await bot.start_polling()

asyncio.run(main())
```

مثال وب‌هوک (FastAPI)

```python
import os
from fastapi import FastAPI
from pyjetra import JetraBot, CommandFilter, make_asgi_handler

app = FastAPI()
bot = JetraBot(os.environ["JETRA_TOKEN"])

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    msg.reply("سلام از وب‌هوک!")

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

لینک‌ها

· 📦 PyPI: 
· 📁 گیت‌هاب: 
· 🐛 گزارش مشکل: 
· 🚀 نسخه‌ها: 
· 📖 مستندات Bot API جترا: 
· 💬 کانال PyJetra: 
· 👥 چت جامعه: 

---

About the developer

<div align="center">

Ali VEX

Founder and lead developer of PyJetra
Bot developer, Python enthusiast, Jetra community member

</div>

Ali VEX is a Python developer who created PyJetra, a Python library for the
Jetra Bot API. He is active in the Jetra developer community and maintains
JetraGuard, a group-management bot built on top of PyJetra.

Contact

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

Made with ❤️ for the Jetra community

ساخته‌شده با ❤️ برای جامعه‌ی جترا

</div>
```