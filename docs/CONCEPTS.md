# مفاهیم کلیدی pyjetra

## 1. دو بخش pyjetra

pyjetra از دو زیرپکیج مستقل تشکیل شده:

| بخش | کاربرد | نوع اتصال |
|-----|--------|-----------|
| `pyjetra.botapi` | ربات‌ها (Bot API) | HTTP |
| `pyjetra.userapi` | اکانت کاربری واقعی | WebSocket |

نصب جداگانه: `pip install pyjetra[bot]` یا `pip install pyjetra[user]`.

## 2. Bot API - ساده و محدود

ربات با توکن کار می‌کند. توکن را از @UserBoT روی جترا بگیرید.

- درخواست‌ها HTTP POST هستند.
- محدودیت آپلود: ۲۵ مگابایت.
- long polling حداکثر ۵۰ ثانیه و ۱۰۰ آپدیت.
- دریافت آپدیت: `bot.poll()` یا webhook.

## 3. User API - قدرتمند و پیچیده

اکانت کاربری از طریق پروتکل MTProto-style روی WebSocket وصل می‌شود.

### 3.1. لاگین

سه مرحله:
1. `send_code(phone)` - ارسال کد SMS
2. `sign_in(phone, phone_code_hash, code)` - تایید کد
3. اگر 2FA فعال باشد: `check_password(password)` - با SRP

نتیجه در `~/.pyjetra/jetra_session.json` ذخیره می‌شود. شامل `auth_key` است - هرگز به اشتراک نگذارید.

### 3.2. access_hash

هر کاربر/گروه/کانال دو شناسه دارد:
- `id`: شناسه‌ی دائمی
- `access_hash`: شناسه‌ی مخفی که سرور به هر اکانت اختصاص می‌دهد

برای فراخوانی متدهایی مثل `sendMessage` به کاربر دیگر، به `access_hash` او نیاز دارید. منابع:
- `get_dialogs` (لیست چت‌ها)
- `resolve_username`
- `get_participants` (اعضای گروه)

pyjetra به صورت خودکار `access_hash` را در `~/.pyjetra/jetra_local.db` ذخیره می‌کند.

### 3.3. peer_type

هر peer یا `user` است یا `group` (کانال/سوپرگروه). تفاوت در سریالایز TL:
- `InputPeerUser`: 0xDDE8A54C
- `InputPeerChannel`: 0x27BCBBFC

اگر `peer_type` را ندهید، pyjetra از دیتابیس محلی تشخیص می‌دهد.

### 3.4. پاسخ‌های raw

اکثر متدهای userapi بایت‌های خام TL برمی‌گردانند. برای متدهای پرکاربرد مثل `send_message`، خروجی پارس می‌شود و `msg_id` واقعی برگردانده می‌شود. برای بقیه باید خودتان بایت‌ها را پارس کنید یا از هلپرهای داخلی استفاده کنید.

## 4. FSM (Finite State Machine)

در botapi، یک دیکشنری ساده در حافظه نگه می‌دارد کاربر در چه وضعیتی است:

    bot.set_state(user_id, "awaiting_phone")
    state = bot.get_state(user_id)  # "awaiting_phone"
    bot.clear_state(user_id)

این حالت با ری‌استارت ربات از بین می‌رود. برای ماندگاری از دیتابیس استفاده کنید.

## 5. Long polling vs Webhook

| روش | مزیت | عیب |
|-----|------|-----|
| `bot.poll()` | ساده، بدون سرور | مناسب ترافیک بالا نیست |
| Webhook | مقیاس‌پذیر، realtime | نیاز به HTTPS و سرور |

برای webhook از `make_wsgi_handler` (Flask/Django) یا `make_asgi_handler` (FastAPI/Starlette) استفاده کنید.

## 6. session file

فایل `~/.pyjetra/jetra_session.json` شامل:
- `auth_key`: کلید رمزنگاری (۲۵۶ بایت)
- `auth_key_id`: ۸ بایت آخر SHA1 از auth_key
- `server_salt`: salt برای رمزنگاری پیام‌ها
- `user_id`: شناسه‌ی کاربر لاگین‌شده
- `access_hash`: access_hash خود کاربر

اگر این فایل پاک شود باید دوباره لاگین کنید. اگر لو برود فرد می‌تواند به اکانت شما دسترسی پیدا کند.

مسیر ذخیره‌سازی را می‌توان با متغیر محیطی `PYJETRA_DATA_DIR` تغییر داد.
