# PyJetra Library
### [EN] A Modern Python Wrapper for Jetra Bot API
### [FA] یک کتابخانه مدرن پایتون برای API ربات جترا

---

## [EN] Features / [FA] امکانات
* **Sync & Async Support** / پشتیبانی از Sync و Async
* **State Management** / مدیریت وضعیت
* **Advanced Filters** / فیلترهای پیشرفته
* **Full Media Support** / پشتیبانی کامل از رسانه‌ها

## [EN] Installation / [FA] نصب
```bash
pip install requests aiohttp
```

## [EN] Quick Start (Sync) / [FA] شروع سریع (همزمان)
```python
from pyjetra import JetraBot, CommandFilter

bot = JetraBot('YOUR_TOKEN')

@bot.on_message(filters=[CommandFilter('start')])
def start(msg):
    msg.reply('Hello from PyJetra!')

bot.poll()
```

## [EN] Quick Start (Async) / [FA] شروع سریع (غیرهمزمان)
```python
from pyjetra import AsyncJetraBot, CommandFilter
import asyncio

bot = AsyncJetraBot('YOUR_TOKEN')

@bot.on_message(filters=[CommandFilter('start')])
async def start(msg):
    await msg.reply('Hello Fast!')

asyncio.run(bot.start_polling())
```

## [EN] Testing / [FA] تست کردن
Navigate to the `tests/` folder and run the files.
Read the comments inside each test file.

## [EN] Developer / [FA] توسعه‌دهنده
Created with ❤️ by Ali VEX
GitHub: https://github.com/lyrdaadhrpyk802-ux