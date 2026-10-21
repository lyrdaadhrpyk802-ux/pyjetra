import requests
import time
from typing import List, Optional, Callable, Any
from .exceptions import JetraError
from .types import User, Message, CallbackQuery, InlineKeyboardMarkup

class JetraBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://jetra.ir/bot{token}/"
        self.session = requests.Session()
        self._message_handlers = []
        self._callback_handlers = []
        self._states = {}

    def set_state(self, user_id, state): self._states[user_id] = state
    def get_state(self, user_id): return self._states.get(user_id)
    def clear_state(self, user_id):
        if user_id in self._states: del self._states[user_id]

    def _request(self, method: str, **params) -> Any:
        url = self.base_url + method
        try:
            response = self.session.post(url, json=params, timeout=30)
            data = response.json()
            if not data.get("ok"): raise JetraError(f"API Error: {data.get('description')}")
            return data.get("result")
        except requests.exceptions.ReadTimeout: return []
        except Exception as e: raise JetraError(f"Network Error: {e}")

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("sendMessage", **params)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
        return self._request("answerCallbackQuery", **params)

    def get_updates(self, offset: int = 0) -> List[dict]:
        return self._request("getUpdates", offset=offset, timeout=30)

    def on_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._message_handlers.append({"func": f, "filters": filters or []})
            return f
        return decorator(func) if func else decorator

    def on_callback_query(self, func: Callable):
        self._callback_handlers.append(func)
        return func

    def poll(self):
        print("Bot polling...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        msg = Message(update["message"], self)
                        for handler in self._message_handlers:
                            if all(f(msg) for f in handler["filters"]):
                                handler["func"](msg)
                    elif "callback_query" in update:
                        cb = CallbackQuery(update["callback_query"], self)
                        for handler in self._callback_handlers:
                            handler(cb)
            except Exception:
                time.sleep(2)