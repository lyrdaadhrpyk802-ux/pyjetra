# PyJetra Library
### [EN] A Modern Python Wrapper for Jetra Bot API
### [FA] یک کتابخانه مدرن پایتون برای API ربات جترا

---

## [EN] Features / [FA] امکانات
* Sync & Async Support / پشتیبانی از Sync و Async
* State Management / مدیریت وضعیت
* Advanced Filters / فیلترهای پیشرفته
* Full Media Support / پشتیبانی کامل از رسانه‌ها

## [EN] Installation / [FA] نصب
pip install requests aiohttp

## [EN] Quick Start (Sync) / [FA] شروع سریع
from pyjetra import JetraBot, CommandFilter
bot = JetraBot('YOUR_TOKEN')
@bot.on_message(filters=[CommandFilter('start')])
def start(msg):
    msg.reply('Hello from PyJetra!')
bot.poll()

## [EN] Testing / [FA] تست کردن
Navigate to the tests/ folder and run the files.
Read the comments inside each test file.