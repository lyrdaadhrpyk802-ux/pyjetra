# [EN] PyJetra - Sync client for the Jetra Bot API.
# [FA] PyJetra - Sync client for the Jetra Bot API.

import os
import time
from typing import List, Optional, Callable, Any

import requests

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
        self._edited_message_handlers = []
        self._callback_handlers = []
        self._states = {}

    # ------------------------------------------------------------------
    # State management (FSM)
    # ------------------------------------------------------------------
    def set_state(self, user_id, state):
        self._states[user_id] = state

    def get_state(self, user_id):
        return self._states.get(user_id)

    def clear_state(self, user_id):
        if user_id in self._states:
            del self._states[user_id]

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------
    def _request(self, method: str, files: Optional[dict] = None,
                 http_timeout: int = 30, **params) -> Any:
        url = self.base_url + method
        try:
            if files:
                response = self.session.post(
                    url, data=params, files=files,
                    timeout=max(120, http_timeout),
                )
            else:
                response = self.session.post(url, json=params, timeout=http_timeout)
            if not response.text:
                raise JetraError("Empty response")
            try:
                data = response.json()
            except ValueError:
                raise JetraError(f"Invalid response: {response.text[:100]}")
            if not data.get("ok"):
                raise JetraError(f"API Error: {data.get('description', 'Unknown')}")
            return data.get("result")
        except requests.exceptions.ReadTimeout:
            return []
        except Exception as e:
            raise JetraError(f"Network Error: {e}")


    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    def get_me(self) -> User:
        res = self._request("getMe")
        return User(**{k: res.get(k) for k in
                       ["id", "is_bot", "first_name", "last_name", "username"]})

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------
    def send_message(self, chat_id: int, text: str,
                     reply_to_message_id: Optional[int] = None,
                     reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            params["reply_markup"] = reply_markup.to_dict()
        return self._request("sendMessage", **params)

    def _send_file(self, method: str, field_name: str, chat_id: int,
                   file_path: str, caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, **kwargs}
        if caption:
            params["caption"] = caption
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        try:
            with open(file_path, "rb") as file:
                return self._request(method, files={field_name: file}, **params)
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")

    def send_photo(self, chat_id: int, photo_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendPhoto", "photo", chat_id, photo_path,
                               caption, reply_to_message_id, **kwargs)

    def send_document(self, chat_id: int, document_path: str,
                      caption: Optional[str] = None,
                      reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendDocument", "document", chat_id, document_path,
                               caption, reply_to_message_id, **kwargs)

    def send_video(self, chat_id: int, video_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendVideo", "video", chat_id, video_path,
                               caption, reply_to_message_id, **kwargs)

    def send_audio(self, chat_id: int, audio_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendAudio", "audio", chat_id, audio_path,
                               caption, reply_to_message_id, **kwargs)

    def send_voice(self, chat_id: int, voice_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendVoice", "voice", chat_id, voice_path,
                               caption, reply_to_message_id, **kwargs)

    def send_sticker(self, chat_id: int, sticker_path: str,
                     reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendSticker", "sticker", chat_id, sticker_path,
                               None, reply_to_message_id, **kwargs)

    def send_animation(self, chat_id: int, animation_path: str,
                       caption: Optional[str] = None,
                       reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file("sendAnimation", "animation", chat_id, animation_path,
                               caption, reply_to_message_id, **kwargs)

    # ------------------------------------------------------------------
    # Locations and contacts
    # ------------------------------------------------------------------
    def send_location(self, chat_id: int, latitude: float, longitude: float,
                      reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, "latitude": latitude,
                  "longitude": longitude, **kwargs}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return self._request("sendLocation", **params)

    def send_contact(self, chat_id: int, phone_number: str, first_name: str,
                     last_name: Optional[str] = None,
                     reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, "phone_number": phone_number,
                  "first_name": first_name, **kwargs}
        if last_name:
            params["last_name"] = last_name
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return self._request("sendContact", **params)

    def send_venue(self, chat_id: int, latitude: float, longitude: float,
                   title: str, address: str,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {"chat_id": chat_id, "latitude": latitude, "longitude": longitude,
                  "title": title, "address": address, **kwargs}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return self._request("sendVenue", **params)

    # ------------------------------------------------------------------
    # Editing and deleting
    # ------------------------------------------------------------------
    def edit_message_text(self, chat_id: int, message_id: int, text: str,
                          reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageText", **params)

    def edit_message_caption(self, chat_id: int, message_id: int,
                             caption: str,
                             reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id,
                  "caption": caption}
        if reply_markup:
            params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageCaption", **params)

    def edit_message_media(self, chat_id: int, message_id: int, media: dict,
                           reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id, "media": media}
        if reply_markup:
            params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageMedia", **params)

    def edit_message_reply_markup(self, chat_id: int, message_id: int,
                                  reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            params["reply_markup"] = reply_markup.to_dict()
        return self._request("editMessageReplyMarkup", **params)

    def delete_message(self, chat_id: int, message_id: int) -> dict:
        return self._request("deleteMessage", chat_id=chat_id,
                             message_id=message_id)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
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
            with open(destination_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return destination_path
        except requests.RequestException as e:
            raise JetraError(f"Download failed: {e}")

    # ------------------------------------------------------------------
    # Bot commands
    # ------------------------------------------------------------------
    def set_my_commands(self, commands: List[dict]) -> dict:
        return self._request("setMyCommands", commands=commands)

    def get_my_commands(self) -> List[dict]:
        return self._request("getMyCommands")

    def delete_my_commands(self) -> dict:
        return self._request("deleteMyCommands")

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------
    def set_webhook(self, url: str, secret_token: Optional[str] = None,
                    allowed_updates: Optional[List[str]] = None) -> dict:
        params = {"url": url}
        if secret_token:
            params["secret_token"] = secret_token
        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        return self._request("setWebhook", **params)

    def delete_webhook(self) -> dict:
        return self._request("deleteWebhook")

    def get_webhook_info(self) -> dict:
        return self._request("getWebhookInfo")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def answer_callback_query(self, callback_query_id: str,
                              text: Optional[str] = None,
                              show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        if show_alert:
            params["show_alert"] = True
        return self._request("answerCallbackQuery", **params)

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------
    def get_updates(self, offset: int = 0,
                    allowed_updates: Optional[List[str]] = None) -> List[dict]:
        params = {"offset": offset, "timeout": 30}
        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        return self._request("getUpdates", http_timeout=40, **params)

    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------
    def on_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._message_handlers.append({"func": f, "filters": filters or []})
            return f
        return decorator(func) if func else decorator

    def on_edited_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._edited_message_handlers.append({"func": f, "filters": filters or []})
            return f
        return decorator(func) if func else decorator

    def on_callback_query(self, func: Callable = None):
        def decorator(f):
            self._callback_handlers.append(f)
            return f
        return decorator(func) if func else decorator

    # ------------------------------------------------------------------
    # Update processing
    # ------------------------------------------------------------------
    def process_update(self, update: dict):
        if "message" in update:
            msg = Message(update["message"], self)
            for handler in self._message_handlers:
                if all(f(msg) for f in handler["filters"]):
                    handler["func"](msg)
        elif "edited_message" in update:
            msg = Message(update["edited_message"], self)
            for handler in self._edited_message_handlers:
                if all(f(msg) for f in handler["filters"]):
                    handler["func"](msg)
        elif "callback_query" in update:
            cb = CallbackQuery(update["callback_query"], self)
            for handler in self._callback_handlers:
                handler(cb)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------
    def poll(self, allowed_updates: Optional[List[str]] = None):
        print("Bot is polling (Sync)...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(offset, allowed_updates=allowed_updates)
                for update in updates:
                    offset = update["update_id"] + 1
                    self.process_update(update)
            except Exception as e:
                print(f"[Polling Error] {e}")
                time.sleep(2)
