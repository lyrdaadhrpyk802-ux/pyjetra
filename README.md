

```markdown
<div align="center">

<img src="https://raw.githubusercontent.com/lyrdaadhrpyk802-ux/pyjetra/main/logo.png" width="220" alt="PyJetra Logo">

# PyJetra

**A modern, bilingual (Sync & Async) Python wrapper for the Jetra Bot API**

[![PyPI version](https://img.shields.io/pypi/v/pyjetra?style=for-the-badge&logo=pypi&color=blue)](https://pypi.org/project/pyjetra/)
[![PyPI downloads](https://img.shields.io/pypi/dm/pyjetra?style=for-the-badge&color=purple)](https://pypi.org/project/pyjetra/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyjetra?style=for-the-badge&logo=python)](https://pypi.org/project/pyjetra/)
[![License](https://img.shields.io/github/license/lyrdaadhrpyk802-ux/pyjetra?style=for-the-badge&color=orange)](LICENSE)

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

- Sync and async clients (`JetraBot` and `AsyncJetraBot`)
- Full Bot API coverage: messages, media, edits, deletes, callbacks, webhooks
- FSM state management for step-by-step conversations
- Inline keyboards with multi-level menus, URL buttons, and callbacks
- Filters: `CommandFilter`, `TextFilter`, `RegexFilter`
- Edited message events via `on_edited_message`
- Media support: photo, document, video, audio, voice, sticker,
  animation, location, contact, venue, live photo
- Webhook ready: `set_webhook`, `delete_webhook`, `get_webhook_info`
- Rich `Message` type: replies, forwards, service events
- Pythonic: type hints, clean dataclasses, no boilerplate

### Installation

```bash
pip install pyjetra
```

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

bot = AsyncJetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
async def start(msg):
    await msg.reply("Hello from Async PyJetra!")

asyncio.run(bot.start_polling())
```

Links

· PyPI: 
· GitHub: 
· Issues: 
· Releases: 

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

· کلاینت همگام و ناهمگام (JetraBot و AsyncJetraBot)
· پوشش کامل Bot API: پیام، رسانه، ویرایش، حذف، کال‌بک، وب‌هوک
· مدیریت وضعیت (FSM) برای گفتگوهای چندمرحله‌ای
· دکمه‌های شیشه‌ای با منوهای چندسطحی، دکمه‌های لینک و کال‌بک
· فیلترها: CommandFilter، TextFilter، RegexFilter
· رویداد ویرایش پیام با on_edited_message
· پشتیبانی رسانه: عکس، فایل، ویدیو، صدا، ویس، استیکر، انیمیشن،
  موقعیت، مخاطب، مکان، لایو فوتو
· آماده‌ی وب‌هوک: set_webhook، delete_webhook، get_webhook_info
· تایپ کامل Message: پاسخ‌ها، فوروارد، رویدادهای سرویس
· پایتونیک: type hint، dataclass تمیز، بدون کد اضافه

نصب

```bash
pip install pyjetra
```

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

لینک‌ها

· PyPI: 
· گیت‌هاب: 
· گزارش مشکل: 

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

· Jetra profile: 
· PyJetra channel: 
· Community chat: 
· GitHub: 
· Email: 

---

License

Released under the MIT License. See the LICENSE file for details.

```

