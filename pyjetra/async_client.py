import aiohttp
import asyncio
from typing import List, Optional, Callable, Any
from .exceptions import JetraError
from .types import User, Message, CallbackQuery, InlineKeyboardMarkup

class AsyncJetraBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://jetra.ir/bot{token}/"
        self._message_handlers = []
        self._callback_handlers = []

    async def _request(self, method: str, **params) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url + method, json=params) as resp:
                data = await resp.json()
                if not data.get("ok"): raise JetraError(f"API Error: {data.get('description')}")
                return data.get("result")

    async def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return await self._request("sendMessage", **params)

    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> dict:
        return await self._request("answerCallbackQuery", callback_query_id=callback_query_id, text=text, show_alert=show_alert)

    async def get_updates(self, offset: int = 0) -> List[dict]:
        return await self._request("getUpdates", offset=offset, timeout=30)

    def on_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._message_handlers.append({"func": f, "filters": filters or []})
            return f
        return decorator(func) if func else decorator

    def on_callback_query(self, func: Callable):
        self._callback_handlers.append(func)
        return func

    async def start_polling(self):
        print("Async Bot polling...")
        offset = 0
        while True:
            try:
                updates = await self.get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        msg = Message(update["message"], self)
                        for handler in self._message_handlers:
                            if all(f(msg) for f in handler["filters"]):
                                await handler["func"](msg)
                    elif "callback_query" in update:
                        cb = CallbackQuery(update["callback_query"], self)
                        for handler in self._callback_handlers:
                            await handler(cb)
            except Exception:
                await asyncio.sleep(2)