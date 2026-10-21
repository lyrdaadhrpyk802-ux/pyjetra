#!/bin/bash

cd /storage/emulated/0/pyjetra || exit 1

# 1. Update client.py with all methods
cat << 'PYEOF' > pyjetra/client.py
import requests
import time
import os
from typing import List, Optional, Callable, Any, Union
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

    # --- Core Methods ---
    def get_me(self) -> User:
        result = self._request("getMe")
        return User(**{k: result.get(k) for k in ["id", "is_bot", "first_name", "last_name", "username"]})

    def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id: params["reply_to_message_id"] = reply_to_message_id
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("sendMessage", **params)

    def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup: params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageText", **params)

    def delete_message(self, chat_id: int, message_id: int) -> dict:
        return self._request("deleteMessage", chat_id=chat_id, message_id=message_id)

    # --- Media Uploads ---
    def _send_file(self, method: str, field_name: str, chat_id: int, file_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, **kwargs}
        if caption: params["caption"] = caption
        try:
            with open(file_path, "rb") as file:
                return self._request(method, files={field_name: file}, **params)
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")

    def send_photo(self, chat_id: int, photo_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendPhoto", "photo", chat_id, photo_path, caption, **kwargs)

    def send_document(self, chat_id: int, document_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendDocument", "document", chat_id, document_path, caption, **kwargs)

    def send_video(self, chat_id: int, video_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendVideo", "video", chat_id, video_path, caption, **kwargs)

    def send_audio(self, chat_id: int, audio_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendAudio", "audio", chat_id, audio_path, caption, **kwargs)

    def send_voice(self, chat_id: int, voice_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendVoice", "voice", chat_id, voice_path, caption, **kwargs)

    def send_sticker(self, chat_id: int, sticker_path: str, **kwargs) -> dict:
        return self._send_file("sendSticker", "sticker", chat_id, sticker_path, None, **kwargs)

    def send_animation(self, chat_id: int, animation_path: str, caption: Optional[str] = None, **kwargs) -> dict:
        return self._send_file("sendAnimation", "animation", chat_id, animation_path, caption, **kwargs)

    # --- Locations & Contacts ---
    def send_location(self, chat_id: int, latitude: float, longitude: float, **kwargs) -> dict:
        params = {"chat_id": chat_id, "latitude": latitude, "longitude": longitude, **kwargs}
        return self._request("sendLocation", **params)

    def send_contact(self, chat_id: int, phone_number: str, first_name: str, last_name: Optional[str] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, "phone_number": phone_number, "first_name": first_name, **kwargs}
        if last_name: params["last_name"] = last_name
        return self._request("sendContact", **params)

    # --- File Download ---
    def get_file(self, file_id: str) -> dict:
        return self._request("getFile", file_id=file_id)

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

    # --- Bot Commands & Menus ---
    def set_my_commands(self, commands: List[dict]) -> dict:
        """Sets the list of commands in the bot's menu."""
        return self._request("setMyCommands", commands=commands)

    def get_my_commands(self) -> List[dict]:
        return self._request("getMyCommands")

    def delete_my_commands(self) -> dict:
        return self._request("deleteMyCommands")

    def set_chat_menu_button(self, chat_id: Optional[int] = None, menu_button: Optional[dict] = None) -> dict:
        params = {}
        if chat_id: params["chat_id"] = chat_id
        if menu_button: params["menu_button"] = menu_button
        return self._request("setChatMenuButton", **params)

    # --- Callbacks & Updates ---
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

# 2. Update test.py to test new features
cat << 'PYEOF' > test.py
import sys
sys.dont_write_bytecode = True
import os
import time
from pyjetra import JetraBot, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "1780246392:3W4m3UParm6nelq3mS2HmjtgV6_pWiIfCj8"

def main():
    bot = JetraBot(BOT_TOKEN)
    
    # Set up the bot commands menu on startup
    try:
        bot.set_my_commands([
            {"command": "start", "description": "Start the bot"},
            {"command": "edit", "description": "Test editing a message"},
            {"command": "delete", "description": "Test deleting a message"},
            {"command": "location", "description": "Send a location"}
        ])
        print("Commands menu updated.")
    except Exception as e:
        print(f"Failed to set commands: {e}")

    @bot.on_message
    def handle_message(message):
        try:
            if not message.text:
                return

            text = message.text.lower()
            name = message.from_user.first_name if message.from_user else "User"
            print(f"Received: {text}")

            if text == "/start":
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="Option 1", callback_data="opt_1")],
                    [InlineKeyboardButton(text="Visit Website", url="https://jetra.ir")]
                ])
                message.reply(f"Welcome {name}. Please select an option:", reply_markup=keyboard)
            
            elif text == "/edit":
                msg = message.reply("This message will be edited in 2 seconds...")
                time.sleep(2)
                bot.edit_message_text(
                    chat_id=message.chat.id, 
                    message_id=msg["message_id"], 
                    text="The message has been edited!"
                )
                print("Message edited.")

            elif text == "/delete":
                msg = message.reply("This message will self-destruct in 2 seconds...")
                time.sleep(2)
                bot.delete_message(chat_id=message.chat.id, message_id=msg["message_id"])
                print("Message deleted.")

            elif text == "/location":
                message.reply("Here is a location:")
                bot.send_location(message.chat.id, latitude=35.6892, longitude=51.3890)
                print("Location sent.")

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

echo "Library updated to version 2.0 successfully!"
