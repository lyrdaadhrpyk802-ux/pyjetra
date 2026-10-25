# [EN] PyJetra - Synchronous client for the Jetra Bot API.

import time
from typing import Any, Callable, List, Optional

import requests

from .exceptions import JetraError
from .types import (
    User,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    ChatMember,
    ChatMemberUpdated,
)


def _to_dict(value):
    """Convert a value to a dict if it has ``to_dict()``, else return as-is."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


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
        self._chat_member_handlers = []
        self._my_chat_member_handlers = []
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
                    url,
                    data=params,
                    files=files,
                    timeout=max(120, http_timeout),
                )
            else:
                response = self.session.post(
                    url, json=params, timeout=http_timeout
                )
            if not response.text:
                raise JetraError("Empty response")
            try:
                data = response.json()
            except ValueError:
                raise JetraError(
                    f"Invalid response: {response.text[:100]}"
                )
            if not data.get("ok"):
                raise JetraError(
                    f"API Error: {data.get('description', 'Unknown')}"
                )
            return data.get("result")
        except requests.exceptions.ReadTimeout:
            return []
        except JetraError:
            raise
        except Exception as e:
            raise JetraError(f"Network Error: {e}")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    def get_me(self) -> User:
        res = self._request("getMe") or {}
        return User(
            id=res.get("id", 0),
            is_bot=res.get("is_bot", False),
            first_name=res.get("first_name", ""),
            last_name=res.get("last_name"),
            username=res.get("username"),
        )

    # ------------------------------------------------------------------
    # Group and member management
    # ------------------------------------------------------------------
    def get_chat(self, chat_id) -> dict:
        return self._request("getChat", chat_id=chat_id)

    def get_chat_member(self, chat_id, user_id) -> ChatMember:
        res = self._request(
            "getChatMember", chat_id=chat_id, user_id=user_id
        ) or {}
        return ChatMember.from_dict(res)

    def get_chat_administrators(self, chat_id,
                                return_bots: bool = False) -> List[ChatMember]:
        params = {"chat_id": chat_id}
        if return_bots:
            params["return_bots"] = True
        res = self._request("getChatAdministrators", **params) or []
        return [ChatMember.from_dict(m) for m in res]

    def get_chat_member_count(self, chat_id) -> int:
        return self._request("getChatMemberCount", chat_id=chat_id)

    def ban_chat_member(self, chat_id, user_id,
                        until_date: Optional[int] = None) -> dict:
        params = {"chat_id": chat_id, "user_id": user_id}
        if until_date:
            params["until_date"] = until_date
        return self._request("banChatMember", **params)

    def unban_chat_member(self, chat_id, user_id,
                          only_if_banned: bool = False) -> dict:
        params = {"chat_id": chat_id, "user_id": user_id}
        if only_if_banned:
            params["only_if_banned"] = True
        return self._request("unbanChatMember", **params)

    def restrict_chat_member(self, chat_id, user_id, permissions,
                             use_independent_chat_permissions: bool = False,
                             until_date: Optional[int] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": _to_dict(permissions),
        }
        if use_independent_chat_permissions:
            params["use_independent_chat_permissions"] = True
        if until_date:
            params["until_date"] = until_date
        return self._request("restrictChatMember", **params)

    def set_chat_permissions(self, chat_id, permissions,
                             use_independent_chat_permissions: bool = False) -> dict:
        params = {
            "chat_id": chat_id,
            "permissions": _to_dict(permissions),
        }
        if use_independent_chat_permissions:
            params["use_independent_chat_permissions"] = True
        return self._request("setChatPermissions", **params)

    def leave_chat(self, chat_id) -> dict:
        return self._request("leaveChat", chat_id=chat_id)

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
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("sendMessage", **params)

    def send_rich_message(self, chat_id: int, text: str,
                          reply_to_message_id: Optional[int] = None,
                          reply_markup: Optional[InlineKeyboardMarkup] = None,
                          **kwargs) -> dict:
        params = {"chat_id": chat_id, "text": text, **kwargs}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("sendRichMessage", **params)

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
                return self._request(
                    method, files={field_name: file}, **params
                )
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")

    def send_photo(self, chat_id: int, photo_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendPhoto", "photo", chat_id, photo_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_live_photo(self, chat_id: int, photo_path: str,
                        caption: Optional[str] = None,
                        reply_to_message_id: Optional[int] = None,
                        **kwargs) -> dict:
        return self._send_file(
            "sendLivePhoto", "photo", chat_id, photo_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_document(self, chat_id: int, document_path: str,
                      caption: Optional[str] = None,
                      reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendDocument", "document", chat_id, document_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_video(self, chat_id: int, video_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendVideo", "video", chat_id, video_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_video_note(self, chat_id: int, video_note_path: str,
                        reply_to_message_id: Optional[int] = None,
                        **kwargs) -> dict:
        return self._send_file(
            "sendVideoNote", "video_note", chat_id, video_note_path,
            None, reply_to_message_id, **kwargs
        )

    def send_audio(self, chat_id: int, audio_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendAudio", "audio", chat_id, audio_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_voice(self, chat_id: int, voice_path: str,
                   caption: Optional[str] = None,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendVoice", "voice", chat_id, voice_path,
            caption, reply_to_message_id, **kwargs
        )

    def send_sticker(self, chat_id: int, sticker_path: str,
                     reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendSticker", "sticker", chat_id, sticker_path,
            None, reply_to_message_id, **kwargs
        )

    def send_animation(self, chat_id: int, animation_path: str,
                       caption: Optional[str] = None,
                       reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        return self._send_file(
            "sendAnimation", "animation", chat_id, animation_path,
            caption, reply_to_message_id, **kwargs
        )

    # ------------------------------------------------------------------
    # Locations and contacts
    # ------------------------------------------------------------------
    def send_location(self, chat_id: int, latitude: float, longitude: float,
                      reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
            **kwargs,
        }
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return self._request("sendLocation", **params)

    def send_contact(self, chat_id: int, phone_number: str, first_name: str,
                     last_name: Optional[str] = None,
                     reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {
            "chat_id": chat_id,
            "phone_number": phone_number,
            "first_name": first_name,
            **kwargs,
        }
        if last_name:
            params["last_name"] = last_name
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return self._request("sendContact", **params)

    def send_venue(self, chat_id: int, latitude: float, longitude: float,
                   title: str, address: str,
                   reply_to_message_id: Optional[int] = None, **kwargs) -> dict:
        params = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
            "title": title,
            "address": address,
            **kwargs,
        }
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
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editMessageText", **params)

    def edit_message_caption(self, chat_id: int, message_id: int,
                             caption: str,
                             reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editMessageCaption", **params)

    def edit_message_media(self, chat_id: int, message_id: int, media: dict,
                           reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "media": _to_dict(media),
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editMessageMedia", **params)

    def edit_message_reply_markup(self, chat_id: int, message_id: int,
                                  reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editMessageReplyMarkup", **params)

    def delete_message(self, chat_id: int, message_id: int) -> dict:
        return self._request(
            "deleteMessage", chat_id=chat_id, message_id=message_id
        )

    # ------------------------------------------------------------------
    # Ephemeral messages (Jetra-specific)
    # ------------------------------------------------------------------
    def edit_ephemeral_message_text(self, chat_id: int, message_id: int,
                                    text: str,
                                    reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editEphemeralMessageText", **params)

    def edit_ephemeral_message_caption(self, chat_id: int, message_id: int,
                                       caption: str,
                                       reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editEphemeralMessageCaption", **params)

    def edit_ephemeral_message_media(self, chat_id: int, message_id: int,
                                     media: dict,
                                     reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "media": _to_dict(media),
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editEphemeralMessageMedia", **params)

    def edit_ephemeral_message_reply_markup(self, chat_id: int, message_id: int,
                                            reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return self._request("editEphemeralMessageReplyMarkup", **params)

    def delete_ephemeral_message(self, chat_id: int, message_id: int) -> dict:
        return self._request(
            "deleteEphemeralMessage",
            chat_id=chat_id,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def get_file(self, file_id: str) -> dict:
        return self._request("getFile", file_id=file_id)

    def download_file(self, file_id: str, destination_path: str) -> str:
        file_info = self.get_file(file_id) or {}
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
    # Menu button and mini-app
    # ------------------------------------------------------------------
    def set_chat_menu_button(self, chat_id=None, menu_button=None) -> dict:
        params = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        if menu_button is not None:
            params["menu_button"] = _to_dict(menu_button)
        return self._request("setChatMenuButton", **params)

    def get_chat_menu_button(self, chat_id=None) -> dict:
        params = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        return self._request("getChatMenuButton", **params)

    def set_user_emoji_status(self, user_id: int,
                              emoji_status_custom_emoji_id: Optional[str] = None,
                              emoji_status_expiration_date: Optional[int] = None) -> dict:
        params = {"user_id": user_id}
        if emoji_status_custom_emoji_id:
            params["emoji_status_custom_emoji_id"] = (
                emoji_status_custom_emoji_id
            )
        if emoji_status_expiration_date:
            params["emoji_status_expiration_date"] = (
                emoji_status_expiration_date
            )
        return self._request("setUserEmojiStatus", **params)

    def answer_web_app_query(self, web_app_query_id: str, result) -> dict:
        return self._request(
            "answerWebAppQuery",
            web_app_query_id=web_app_query_id,
            result=_to_dict(result),
        )

    def save_prepared_inline_message(
        self,
        user_id: int,
        result,
        allow_user_chats: Optional[bool] = None,
        allow_bot_chats: Optional[bool] = None,
        allow_group_chats: Optional[bool] = None,
        allow_channel_chats: Optional[bool] = None,
    ) -> dict:
        params = {"user_id": user_id, "result": _to_dict(result)}
        if allow_user_chats is not None:
            params["allow_user_chats"] = allow_user_chats
        if allow_bot_chats is not None:
            params["allow_bot_chats"] = allow_bot_chats
        if allow_group_chats is not None:
            params["allow_group_chats"] = allow_group_chats
        if allow_channel_chats is not None:
            params["allow_channel_chats"] = allow_channel_chats
        return self._request("savePreparedInlineMessage", **params)

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
            self._message_handlers.append(
                {"func": f, "filters": filters or []}
            )
            return f

        return decorator(func) if func else decorator

    def on_edited_message(self, func: Callable = None, filters: list = None):
        def decorator(f):
            self._edited_message_handlers.append(
                {"func": f, "filters": filters or []}
            )
            return f

        return decorator(func) if func else decorator

    def on_callback_query(self, func: Callable = None):
        def decorator(f):
            self._callback_handlers.append(f)
            return f

        return decorator(func) if func else decorator

    def on_chat_member(self, func: Callable = None):
        def decorator(f):
            self._chat_member_handlers.append(f)
            return f

        return decorator(func) if func else decorator

    def on_my_chat_member(self, func: Callable = None):
        def decorator(f):
            self._my_chat_member_handlers.append(f)
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
        elif "chat_member" in update:
            event = ChatMemberUpdated(update["chat_member"], self)
            for handler in self._chat_member_handlers:
                handler(event)
        elif "my_chat_member" in update:
            event = ChatMemberUpdated(update["my_chat_member"], self)
            for handler in self._my_chat_member_handlers:
                handler(event)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------
    def poll(self, allowed_updates: Optional[List[str]] = None):
        print("Bot is polling (Sync)...")
        offset = 0
        while True:
            try:
                updates = self.get_updates(
                    offset, allowed_updates=allowed_updates
                )
                for update in updates:
                    offset = update["update_id"] + 1
                    self.process_update(update)
            except Exception as e:
                print(f"[Polling Error] {e}")
                time.sleep(2)
