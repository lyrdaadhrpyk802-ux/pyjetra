import requests
import time
from typing import List, Optional, Callable, Any
from .exceptions import JetraError
from .types import User, Message, CallbackQuery, InlineKeyboardMarkup

class JetraBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://jetra.ir/bot{token}/"
        self.file_url = f"https://jetra.ir/file/bot{token}/"
        self.session = requests.Session()
        self._message_handlers = []
        self._callback_handlers = []
        self._states = {}

    # [FA] تنظیم وضعیت کاربر
    def set_state(self, user_id, state): self._states[user_id] = state
    # [FA] دریافت وضعیت کاربر
    def get_state(self, user_id): return self._states.get(user_id)
    # [FA] پاک کردن وضعیت کاربر
    def clear_state(self, user_id):
        if user_id in self._states: del self._states[user_id]

    def _request(self, method: str, files: Optional[dict] = None, http_timeout: int = 30, **params) -> Any:
        url = self.base_url + method
        try:
            if files:
                response = self.session.post(url, data=params, files=files, timeout=max(120, http_timeout))
            else:
                response = self.session.post(url, json=params, timeout=http_timeout)
            if not response.text: raise JetraError("Empty response")
            try:
                data = response.json()
            except ValueError:
                raise JetraError(f"Invalid response: {response.text[:100]}")
            if not data.get("ok"): raise JetraError(f"API Error: {data.get('description', 'Unknown')}")
            return data.get("result")
        except requests.exceptions.ReadTimeout: return []
        except Exception as e: raise JetraError(f"Network Error: {e}")

    # [FA] دریافت اطلاعات ربات
    def get_me(self) -> User:
        res = self._request("getMe")
        return User(**{k: res.get(k) for k in ["id", "is_bot", "first_name", "last_name", "username"]})

    # [FA] ارسال پیام متنی
    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("sendMessage", **params)

    # [FA] ویرایش متن یک پیام ارسال شده
    def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageText", **params)
        
    # [FA] حذف یک پیام
    def delete_message(self, chat_id: int, message_id: int) -> dict:
        return self._request("deleteMessage", chat_id=chat_id, message_id=message_id)

    def _send_file(self, method: str, field_name: str, chat_id: int, file_path: str, caption: Optional[str] = None, reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, **kwargs}
        if caption: params["caption"] = caption
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        try:
            with open(file_path, "rb") as file:
                return self._request(method, files={field_name: file}, **params)
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")

    # [FA] ارسال عکس
    def send_photo(self, chat_id: int, photo_path: str, caption: Optional[str] = None, reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendPhoto", "photo", chat_id, photo_path, caption, reply_to_message_id, **kwargs)

    # [FA] ارسال فایل داکیومنت
    def send_document(self, chat_id: int, document_path: str, caption: Optional[str] = None, reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendDocument", "document", chat_id, document_path, caption, reply_to_message_id, **kwargs)

    # [FA] ارسال ویدیو
    def send_video(self, chat_id: int, video_path: str, caption: Optional[str] = None, reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendVideo", "video", chat_id, video_path, caption, reply_to_message_id, **kwargs)

    def get_file(self, file_id: str) -> dict:
        return self._request("getFile", file_id=file_id)

    # [FA] دانلود فایل از سرور جترا به حافظه
    def download_file(self, file_id: str, destination_path: str) -> str:
        file_info = self.get_file(file_id)
        file_path = file_info.get("file_path")
        if not file_path: raise JetraError("File path not found.")
        download_url = self.file_url + file_path
        try:
            response = self.session.get(download_url, stream=True, timeout=120)
            response.raise_for_status()
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return destination_path
        except requests.RequestException as e:
            raise JetraError(f"Download failed: {e}")

    # [FA] تنظیم منوی دستورات ربات
    def set_my_commands(self, commands: List[dict]) -> dict:
        return self._request("setMyCommands", commands=commands)

    def get_my_commands(self) -> List[dict]:
        return self._request("getMyCommands")

    def delete_my_commands(self) -> dict:
        return self._request("deleteMyCommands")

    def get_webhook_info(self) -> dict:
        return self._request("getWebhookInfo")

    def delete_webhook(self) -> dict:
        return self._request("deleteWebhook")

    # [FA] پاسخ به کلیک دکمه‌های شیشه‌ای
    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id}
        if text: params["text"] = text
        if show_alert: params["show_alert"] = True
        return self._request("answerCallbackQuery", **params)

    # [FA] دریافت پیام‌های جدید از سرور
    def get_updates(self, offset: int = 0) -> List[dict]:
        return self._request("getUpdates", offset=offset, timeout=30, http_timeout=40)

    def on_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._message_handlers.append({"func": f, "filters": filters or []})
            return f
        return decorator(func) if func else decorator

    def on_callback_query(self, func: Callable = None):
        def decorator(f):
            self._callback_handlers.append(f)
            return f
        return decorator(func) if func else decorator

    def process_update(self, update: dict):
        if "message" in update:
            msg = Message(update["message"], self)
            for handler in self._message_handlers:
                if all(f(msg) for f in handler["filters"]):
                    handler["func"](msg)
        elif "callback_query" in update:
            cb = CallbackQuery(update["callback_query"], self)
            for handler in self._callback_handlers:
                handler(cb)

    # [FA] شروع حلقه دریافت پیام‌ها (Long Polling)
    def poll(self):
        print("Bot is polling (Sync)...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    self.process_update(update)
            except Exception as e:
                print(f"[Polling Error] {e}")
                time.sleep(2)
