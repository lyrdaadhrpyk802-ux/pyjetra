```markdown
# PyJetra

یک کتابخانه‌ی مدرن پایتون برای ساخت ربات‌های پیام‌رسان جترا (همگام و ناهمگام).
A modern Python wrapper for the Jetra Bot API (Sync & Async).

![PyJetra Logo](https://raw.githubusercontent.com/lyrdaadhrpyk802-ux/pyjetra/main/logo.png)

## نصب / Installation

```bash
pip install pyjetra
```

نیازمند پایتون ۳.۷ به بالا (Requires Python 3.7+)

امکانات / Features

· پشتیبانی از هر دو حالت همگام (Sync) و ناهمگام (Async)
· پشتیبانی کامل از تمام متدهای Jetra Bot API (پیام، رسانه، وب‌هوک و...)
· مدیریت وضعیت (FSM) برای گفتگوهای چندمرحله‌ای
· دکمه‌های شیشه‌ای (Inline Keyboards) و فیلترهای پیشرفته
· قابلیت استفاده از وب‌هوک با هندلرهای آماده (WSGI/ASGI)

شروع سریع / Quick Start

```python
from pyjetra import JetraBot, CommandFilter

bot = JetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    msg.reply("سلام! PyJetra با موفقیت متصل شد.")

bot.poll()
```

حالت ناهمگام / Async Example

```python
import asyncio
from pyjetra import AsyncJetraBot, CommandFilter

async def main():
    async with AsyncJetraBot("YOUR_BOT_TOKEN") as bot:
        @bot.on_message(filters=[CommandFilter("start")])
        async def start(msg):
            await msg.reply("سلام از حالت Async!")
        
        await bot.start_polling()

asyncio.run(main())
```

مستندات و لینک‌ها / Links

· مستندات رسمی جترا (Jetra Docs): https://jetra.ir/docs/bots
· مخزن گیت‌هاب (GitHub): https://github.com/lyrdaadhrpyk802-ux/pyjetra
· گزارش مشکلات (Issues): https://github.com/lyrdaadhrpyk802-ux/pyjetra/issues

توسعه‌دهنده / Developer

Ali VEX

· پروفایل جترا (Jetra Profile): https://jetra:irUserBoT
· ایمیل (Email): lyrdaadhrpyk802@gmail.com

---

Released under the MIT License.

```