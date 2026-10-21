# PyJetra Library
### [EN] A Modern Python Wrapper for Jetra Bot API
### [FA] یک کتابخانه مدرن پایتون برای API ربات جترا

---

## [EN] Features / [FA] امکانات
* **Sync & Async Support** / پشتیبانی از حالت‌های همزمان و غیرهمزمان
* **State Management** / مدیریت وضعیت (FSM) برای ربات‌های چند مرحله‌ای
* **Advanced Filters** / فیلترهای پیشرفته (Command, Text, Regex)
* **Full Media Support** / پشتیبانی کامل از رسانه‌ها
* **Inline Keyboards** / دکمه‌های شیشه‌ای و مدیریت کلیک‌ها

## [EN] Installation / [FA] نصب
```bash
pip install pyjetra
```

## [EN] Quick Start / [FA] شروع سریع
```python
from pyjetra import JetraBot, CommandFilter

bot = JetraBot('YOUR_TOKEN')

@bot.on_message(filters=[CommandFilter('start')])
def start(msg):
    msg.reply('Hello from PyJetra!')

bot.poll()
```

## [EN] Developer / [FA] توسعه‌دهنده
Created by **Ali VEX**
* GitHub: [lyrdaadhrpyk802-ux](https://github.com/lyrdaadhrpyk802-ux)