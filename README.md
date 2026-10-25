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

**PyJetra** is the first and most complete Python library for building
[Jetra](https://jetra.ir/) bots. It provides a clean, modern interface over
the **Jetra Bot API** with full support for both **synchronous** and
**asynchronous** workflows.

Whether you are building a small personal bot or a large group-management
system, PyJetra gives you all the tools you need without hiding the details.

### Core Features

- **Sync and Async** - `JetraBot` (requests) and `AsyncJetraBot` (aiohttp)
- **Full Bot API coverage** - messages, media, edits, deletes, callbacks, webhooks
- **FSM state management** - step-by-step conversations made easy
- **Inline keyboards** - multi-level menus, URL buttons, callbacks
- **Advanced filters** - `CommandFilter`, `TextFilter`, `RegexFilter`
- **Edited message events** - `@bot.on_edited_message` decorator
- **Full media support** - photo, document, video, audio, voice, sticker, animation, location, contact, venue
- **Webhook ready** - `set_webhook`, `delete_webhook`, `get_webhook_info`
- **Rich Message type** - parses `reply_to_message`, forwards, service events
- **Pythonic** - type hints, clean dataclasses, no boilerplate

### Installation

```bash
pip install pyjetra
```

Quick Start

```python
from pyjetra import JetraBot, CommandFilter, InlineKeyboardMarkup, InlineKeyboardButton

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
        cb.answer("PyJetra - Modern Python wrapper for Jetra Bot API")

bot.poll()
```

Async Example

```python
import asyncio
from pyjetra import AsyncJetraBot, CommandFilter

bot = AsyncJetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
async def start(msg):
    await msg.reply("Hello from Async PyJetra!")

asyncio.run(bot.start_polling())
```

Documentation and Links

· PyPI: https://pypi.org/project/pyjetra
· GitHub: https://github.com/lyrdaadhrpyk802-ux/pyjetra
· Issues: https://github.com/lyrdaadhrpyk802-ux/pyjetra/issues
· Releases: https://github.com/lyrdaadhrpyk802-ux/pyjetra/releases

---

فارسی

PyJetra چیست؟

PyJetra اولین و کامل‌ترین کتابخانه‌ی پایتون برای ساخت ربات‌های
جترا است. این کتابخانه یک رابط تمیز و مدرن روی
Bot API جترا فراهم می‌کند و از هر دو حالت همگام (Sync) و
ناهمگام (Async) به‌طور کامل پشتیبانی می‌کند.

چه یک ربات شخصی کوچک بسازید و چه یک سیستم مدیریت گروه بزرگ،
PyJetra تمام ابزارهای لازم را در اختیار شما قرار می‌دهد.

امکانات اصلی

· همگام و ناهمگام - JetraBot (requests) و AsyncJetraBot (aiohttp)
· پوشش کامل Bot API - پیام، رسانه، ویرایش، حذف، کلیک‌ها، وب‌هوک
· مدیریت وضعیت (FSM) - گفتگوهای چند مرحله‌ای
· دکمه‌های شیشه‌ای - منوهای چندسطحی، دکمه‌های لینک، کال‌بک
· فیلترهای پیشرفته - دستورات، متن، الگوهای Regex
· رویداد ویرایش پیام - دکوراتور @bot.on_edited_message
· پشتیبانی کامل رسانه - عکس، فایل، ویدیو، صدا، ویس، استیکر، انیمیشن، موقعیت، مخاطب، مکان
· آماده‌ی Webhook - تنظیم، حذف و دریافت اطلاعات وب‌هوک
· تایپ کامل Message - پارس reply_to_message، فوروارد و رویدادهای سرویس
· پایتونیک - type hint، dataclass تمیز، بدون کد اضافه

نصب

```bash
pip install pyjetra
```

شروع سریع

```python
from pyjetra import JetraBot, CommandFilter

bot = JetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    msg.reply("سلام از PyJetra!")

bot.poll()
```

---

About the Developer

<div align="center">

Ali VEX

Founder and Lead Developer of PyJetra

Bot Developer | Python Enthusiast | Jetra Community Member

</div>

Ali VEX is a passionate Python developer who created PyJetra - the first
and most complete Python library for the Jetra Bot API. He is active in the
Jetra developer community and maintains JetraGuard, a full-featured
group-management bot built on top of PyJetra.

His goal: make Jetra bot development accessible, clean, and fun for every
developer, from beginners to professionals.

Connect

Platform Link
Jetra Profile https://jetra.ir/UserBoT
PyJetra Channel https://jetra.ir/pyJetra
Community Chat https://jetra.ir/Chatpyjetra
GitHub https://github.com/lyrdaadhrpyk802-ux/pyjetra
Email lyrdaadhrpyk802@gmail.com

```