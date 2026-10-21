#!/bin/bash
cd /storage/emulated/0/pyjetra || exit 1
mkdir -p pyjetra/types

# 1. test.py (Main runner)
cat << 'PYEOF' > test.py
import sys
sys.dont_write_bytecode = True
import os
from pyjetra import JetraBot, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"

def main():
    bot = JetraBot(BOT_TOKEN)
    try:
        me = bot.get_me()
        print(f"Connection successful. Logged in as: {me.first_name} (@{me.username})")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    @bot.on_message
    def handle_message(message):
        try:
            if message.document:
                file_id = message.document.get("file_id")
                file_name = message.document.get("file_name", "downloaded_file")
                print(f"Downloading file: {file_name}...")
                message.reply(f"Downloading {file_name}, please wait...")
                save_path = os.path.join(os.getcwd(), f"downloaded_{file_name}")
                bot.download_file(file_id, save_path)
                message.reply(f"Successfully downloaded to:\n{save_path}")
                print(f"Download complete: {save_path}")
                return

            if not message.text:
                return

            name = message.from_user.first_name if message.from_user else "User"
            print(f"Received message from {name}: {message.text}")

            if message.text.lower() == "/start":
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="Option 1", callback_data="opt_1")],
                    [InlineKeyboardButton(text="Visit Website", url="https://jetra.ir")]
                ])
                message.reply(f"Welcome {name}. Please select an option:", reply_markup=keyboard)
        except Exception as e:
            print(f"Error handling message: {e}")

    @bot.on_callback_query
    def handle_callback(cb):
        try:
            if cb.data == "opt_1":
                cb.answer("You clicked Option 1 successfully!")
        except Exception as e:
            pass

    print("Starting bot polling...")
    bot.poll()

if __name__ == "__main__":
    main()
PYEOF

# 2. pyjetra/__init__.py
cat << 'PYEOF' > pyjetra/__init__.py
from .client import JetraBot
from .exceptions import JetraError
from .types import (User, Chat, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton)
__all__ = ["JetraBot", "JetraError", "User", "Chat", "Message", "CallbackQuery", "InlineKeyboardMarkup", "InlineKeyboardButton"]
PYEOF

# 3. pyjetra/exceptions.py
cat << 'PYEOF' > pyjetra/exceptions.py
class JetraError(Exception):
    pass
PYEOF

# 4. pyjetra/client.py
cat << 'PYEOF' > pyjetra/client.py
import requests
import time
import os
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

    def _request(self, method: str, files: Optional[dict] = None, http_timeout: int = 30, **params) -> Any:
        url = self.base_url + method
        try:
            if files:
                response = self.session.post(url, data=params, files=files, timeout=max(120, http_timeout))
            else:
                response = self.session.post(url, json=params, timeout=http_timeout)
            if not response.text:
                raise JetraError(f"Empty response (Status: {response.status_code})")
            try:
                data = response.json()
            except ValueError:
                raise JetraError(f"Non-JSON response: {response.text[:100]}")
            if not data.get("ok"):
                raise JetraError(f"API Error: {data.get('description', 'Unknown')}")
            return data.get("result")
        except requests.exceptions.ReadTimeout:
            return []
        except requests.RequestException as e:
            raise JetraError(f"Network Error: {e}")

    def get_me(self) -> User:
        result = self._request("getMe")
        return User(**{k: result.get(k) for k in ["id", "is_bot", "first_name", "last_name", "username"]})

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("sendMessage", **params)

    def send_photo(self, chat_id: int, photo_path: str, caption: Optional[str] = None) -> dict:
        params = {"chat_id": chat_id}
        if caption: params["caption"] = caption
        try:
            with open(photo_path, "rb") as file:
                return self._request("sendPhoto", files={"photo": file}, **params)
        except FileNotFoundError:
            raise JetraError(f"File not found: {photo_path}")

    def get_file(self, file_id: str) -> dict:
        return self._request("getFile", file_id=file_id)

    def download_file(self, file_id: str, destination_path: str) -> str:
        file_info = self.get_file(file_id)
        file_path = file_info.get("file_path")
        if not file_path:
            raise JetraError("File path not found.")
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

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id}
        if text: params["text"] = text
        if show_alert: params["show_alert"] = True
        return self._request("answerCallbackQuery", **params)

    def get_updates(self, offset: int = 0) -> List[dict]:
        return self._request("getUpdates", offset=offset, timeout=30, http_timeout=40)

    def on_message(self, func: Callable[[Message], None]):
        self._message_handlers.append(func)
        return func

    def on_callback_query(self, func: Callable[[CallbackQuery], None]):
        self._callback_handlers.append(func)
        return func

    def process_update(self, update: dict):
        if "message" in update:
            msg = Message(update["message"], self)
            for handler in self._message_handlers: handler(msg)
        elif "callback_query" in update:
            cb = CallbackQuery(update["callback_query"], self)
            for handler in self._callback_handlers: handler(cb)

    def poll(self):
        print("Bot is now polling for updates...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    self.process_update(update)
            except JetraError as e:
                print(f"Polling Error: {e}")
                time.sleep(3)
            except KeyboardInterrupt:
                break
            except Exception as e:
                time.sleep(3)
PYEOF

# 5. pyjetra/types/__init__.py
cat << 'PYEOF' > pyjetra/types/__init__.py
from .user import User
from .chat import Chat
from .message import Message
from .callback import CallbackQuery
from .markup import InlineKeyboardMarkup, InlineKeyboardButton
__all__ = ["User", "Chat", "Message", "CallbackQuery", "InlineKeyboardMarkup", "InlineKeyboardButton"]
PYEOF

# 6. pyjetra/types/user.py
cat << 'PYEOF' > pyjetra/types/user.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
PYEOF

# 7. pyjetra/types/chat.py
cat << 'PYEOF' > pyjetra/types/chat.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class Chat:
    id: int
    type: str
    title: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
PYEOF

# 8. pyjetra/types/markup.py
cat << 'PYEOF' > pyjetra/types/markup.py
from typing import List, Optional

class InlineKeyboardButton:
    def __init__(self, text: str, callback_data: Optional[str] = None, url: Optional[str] = None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

    def to_dict(self) -> dict:
        data = {"text": self.text}
        if self.callback_data: data["callback_data"] = self.callback_data
        if self.url: data["url"] = self.url
        return data

class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard: List[List[InlineKeyboardButton]]):
        self.inline_keyboard = inline_keyboard

    def to_dict(self) -> dict:
        return {"inline_keyboard": [[button.to_dict() for button in row] for row in self.inline_keyboard]}
PYEOF

# 9. pyjetra/types/message.py
cat << 'PYEOF' > pyjetra/types/message.py
from typing import Optional, TYPE_CHECKING
from .user import User
from .chat import Chat

if TYPE_CHECKING:
    from ..client import JetraBot
    from .markup import InlineKeyboardMarkup

class Message:
    def __init__(self, data: dict, bot_instance: 'JetraBot'):
        self.message_id = data.get("message_id")
        chat_data = data.get("chat", {})
        self.chat = Chat(
            id=chat_data.get("id", 0), type=chat_data.get("type", "private"),
            title=chat_data.get("title"), first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"), username=chat_data.get("username")
        )
        self.text = data.get("text")
        self.caption = data.get("caption")
        self.raw = data
        self._bot = bot_instance
        self.document = data.get("document")
        self.photo = data.get("photo")
        
        user_data = data.get("from")
        if user_data:
            self.from_user = User(
                id=user_data.get("id", 0), is_bot=user_data.get("is_bot", False),
                first_name=user_data.get("first_name", ""), last_name=user_data.get("last_name"),
                username=user_data.get("username")
            )
        else:
            self.from_user = None

    def reply(self, text: str, reply_markup: Optional['InlineKeyboardMarkup'] = None) -> dict:
        return self._bot.send_message(self.chat.id, text, reply_to_message_id=self.message_id, reply_markup=reply_markup)
PYEOF

# 10. pyjetra/types/callback.py
cat << 'PYEOF' > pyjetra/types/callback.py
from typing import Optional, TYPE_CHECKING
from .user import User
from .message import Message

if TYPE_CHECKING:
    from ..client import JetraBot

class CallbackQuery:
    def __init__(self, data: dict, bot_instance: 'JetraBot'):
        self.id = data.get("id")
        self.from_user = None
        if "from" in data:
            u = data["from"]
            self.from_user = User(
                id=u.get("id", 0), is_bot=u.get("is_bot", False),
                first_name=u.get("first_name", ""), last_name=u.get("last_name"),
                username=u.get("username")
            )
        self.data = data.get("data")
        self.message = Message(data["message"], bot_instance) if "message" in data else None
        self._bot = bot_instance

    def answer(self, text: Optional[str] = None, show_alert: bool = False) -> dict:
        return self._bot.answer_callback_query(self.id, text, show_alert)
PYEOF

echo "All files rebuilt successfully!"
