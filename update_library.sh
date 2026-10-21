#!/bin/bash

TARGET_DIR="/storage/emulated/0/pyjetra"
cd "$TARGET_DIR" || exit 1

echo "Updating library files..."

# 1. types/message.py (Add media parsing)
cat << 'EOF' > pyjetra/types/message.py
from typing import Optional, TYPE_CHECKING
from .user import User
from .chat import Chat

if TYPE_CHECKING:
    from ..client import JetraBot
    from .markup import InlineKeyboardMarkup

class Message:
    """Represents a message received from a Jetra chat."""
    def __init__(self, data: dict, bot_instance: 'JetraBot'):
        self.message_id = data.get("message_id")
        
        chat_data = data.get("chat", {})
        self.chat = Chat(
            id=chat_data.get("id", 0),
            type=chat_data.get("type", "private"),
            title=chat_data.get("title"),
            first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"),
            username=chat_data.get("username")
        )
        
        self.text = data.get("text")
        self.caption = data.get("caption")
        self.raw = data
        self._bot = bot_instance
        
        # Parse media objects
        self.document = data.get("document")
        self.photo = data.get("photo") # Usually a list of sizes
        self.video = data.get("video")
        self.audio = data.get("audio")
        
        user_data = data.get("from")
        if user_data:
            self.from_user = User(
                id=user_data.get("id", 0),
                is_bot=user_data.get("is_bot", False),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name"),
                username=user_data.get("username")
            )
        else:
            self.from_user = None

    def reply(self, text: str, reply_markup: Optional['InlineKeyboardMarkup'] = None) -> dict:
        """Replies to the current message."""
        return self._bot.send_message(
            self.chat.id, text, reply_to_message_id=self.message_id, reply_markup=reply_markup
        )
EOF

# 2. client.py (Add Download & Webhook Support)
cat << 'EOF' > pyjetra/client.py
import requests
import time
import os
from typing import List, Optional, Callable, Any
from .exceptions import JetraError
from .types import User, Message, CallbackQuery, InlineKeyboardMarkup

class JetraBot:
    """Main client for interacting with the Jetra Bot API."""
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://jetra.ir/bot{token}/"
        self.file_url = f"https://jetra.ir/file/bot{token}/"
        self.session = requests.Session()
        self._message_handlers = []
        self._callback_handlers = []

    def _request(self, method: str, files: Optional[dict] = None, **params) -> Any:
        url = self.base_url + method
        try:
            if files:
                response = self.session.post(url, data=params, files=files, timeout=120)
            else:
                response = self.session.post(url, json=params, timeout=30)
                
            if not response.text:
                raise JetraError(f"Empty response (Status: {response.status_code})")
            try:
                data = response.json()
            except ValueError:
                raise JetraError(f"Non-JSON response: {response.text[:100]}")
            if not data.get("ok"):
                raise JetraError(f"API Error: {data.get('description', 'Unknown')}")
            return data.get("result")
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

    def send_document(self, chat_id: int, document_path: str, caption: Optional[str] = None) -> dict:
        params = {"chat_id": chat_id}
        if caption: params["caption"] = caption
        try:
            with open(document_path, "rb") as file:
                return self._request("sendDocument", files={"document": file}, **params)
        except FileNotFoundError:
            raise JetraError(f"File not found: {document_path}")

    def get_file(self, file_id: str) -> dict:
        """Gets basic info about a file and prepares it for download."""
        return self._request("getFile", file_id=file_id)

    def download_file(self, file_id: str, destination_path: str) -> str:
        """Downloads a file from Jetra servers to the local disk."""
        file_info = self.get_file(file_id)
        file_path = file_info.get("file_path")
        
        if not file_path:
            raise JetraError("File path not found in server response.")
            
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
        return self._request("getUpdates", offset=offset, timeout=30)

    # --- Webhook Methods ---
    def set_webhook(self, url: str, secret_token: Optional[str] = None) -> bool:
        """Sets a webhook for receiving updates."""
        params = {"url": url}
        if secret_token: params["secret_token"] = secret_token
        return self._request("setWebhook", **params)

    def delete_webhook(self) -> bool:
        """Removes the webhook integration."""
        return self._request("deleteWebhook")

    def get_webhook_info(self) -> dict:
        """Gets current webhook status."""
        return self._request("getWebhookInfo")

    # --- Handlers & Polling ---
    def on_message(self, func: Callable[[Message], None]):
        self._message_handlers.append(func)
        return func

    def on_callback_query(self, func: Callable[[CallbackQuery], None]):
        self._callback_handlers.append(func)
        return func

    def process_update(self, update: dict):
        """Processes a single update (useful for Webhooks)."""
        if "message" in update:
            msg = Message(update["message"], self)
            for handler in self._message_handlers:
                handler(msg)
        elif "callback_query" in update:
            cb = CallbackQuery(update["callback_query"], self)
            for handler in self._callback_handlers:
                handler(cb)

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
                print("Bot stopped.")
                break
            except Exception as e:
                print(f"Unexpected Error: {e}")
                time.sleep(3)
EOF

# 3. setup.py (For PIP installation)
cat << 'EOF' > setup.py
from setuptools import setup, find_packages

setup(
    name="pyjetra",
    version="1.0.0",
    author="Your Name",
    description="A Python wrapper for the Jetra Bot API.",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
    ],
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
EOF

# 4. README.md
cat << 'EOF' > README.md
# PyJetra

A modern, asynchronous-friendly (sync core) Python wrapper for the Jetra Bot API.

## Installation
pip install pyjetra

## Quick Start
```python
from pyjetra import JetraBot

bot = JetraBot("YOUR_BOT_TOKEN")

@bot.on_message
def handle_message(message):
    if message.text == "/start":
        message.reply("Hello from PyJetra!")

bot.poll()

