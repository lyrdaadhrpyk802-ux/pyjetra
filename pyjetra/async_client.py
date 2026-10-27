# [EN] PyJetra - Asynchronous client for the Jetra Bot API.

import asyncio
import os
from typing import Any, Callable, List, Optional

import aiohttp

from .exceptions import JetraError, FileTooLargeError
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


# Jetra caps each uploaded file at 25 MB.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class AsyncJetraBot:
    """Async client for interacting with the Jetra Bot API.

    Can be used as an async context manager to ensure the underlying
    aiohttp session is closed:

        async with AsyncJetraBot("TOKEN") as bot:
            await bot.send_message(123, "hi")

    Or close it manually:

        bot = AsyncJetraBot("TOKEN")
        ...
        await bot.close()
    """

    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://jetra.ir/bot{token}/"
        self.file_url = f"https://jetra.ir/file/bot{token}/"
        self._session: Optional[aiohttp.ClientSession] = None

        self._message_handlers = []
        self._edited_message_handlers = []
        self._callback_handlers = []
        self._chat_member_handlers = []
        self._my_chat_member_handlers = []
        self._states = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    async def close(self):
        """Close the underlying aiohttp session if it exists."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
        return False

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
    async def _request(self, method: str, http_timeout: int = 30,
                       **params) -> Any:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        url = self.base_url + method
        try:
            async with self._session.post(
                url, json=params, timeout=http_timeout
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise JetraError(
                        f"HTTP Error {response.status}: {text[:100]}"
                    )
                try:
                    data = await response.json()
                except Exception:
                    text = await response.text()
                    raise JetraError(
                        f"Invalid JSON response: {text[:100]}"
                    )
                if not data.get("ok"):
                    raise JetraError(
                        f"API Error: {data.get('description', 'Unknown')}"
                    )
                return data.get("result")
        except asyncio.TimeoutError:
            return []
        except JetraError:
            raise
        except aiohttp.ClientError as e:
            raise JetraError(f"Network Error: {e}")

    async def _send_file(self, method: str, field_name: str, chat_id: int,
                         file_path: str, caption: Optional[str] = None,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        try:
            size = os.path.getsize(file_path)
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")
        if size > MAX_UPLOAD_BYTES:
            raise FileTooLargeError(
                f"File too large: {size} bytes "
                f"(Jetra limit is {MAX_UPLOAD_BYTES} bytes)"
            )

        url = self.base_url + method
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        if caption:
            data.add_field("caption", caption)
        if reply_to_message_id:
            data.add_field("reply_to_message_id", str(reply_to_message_id))
        for k, v in kwargs.items():
            data.add_field(k, str(v))

        try:
            with open(file_path, "rb") as f:
                data.add_field(
                    field_name, f, filename=os.path.basename(file_path)
                )
                async with self._session.post(
                    url, data=data, timeout=120
                ) as response:
                    res_data = await response.json()
                    if not res_data.get("ok"):
                        raise JetraError(
                            f"API Error: {res_data.get('description')}"
                        )
                    return res_data.get("result")
        except FileNotFoundError:
            raise JetraError(f"File not found: {file_path}")
        except JetraError:
            raise
        except Exception as e:
            raise JetraError(f"Upload failed: {e}")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    async def get_me(self) -> User:
        res = await self._request("getMe") or {}
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
    async def get_chat(self, chat_id) -> dict:
        return await self._request("getChat", chat_id=chat_id)

    async def get_chat_member(self, chat_id, user_id) -> ChatMember:
        res = await self._request(
            "getChatMember", chat_id=chat_id, user_id=user_id
        ) or {}
        return ChatMember.from_dict(res)

    async def get_chat_administrators(self, chat_id,
                                      return_bots: bool = False) -> List[ChatMember]:
        params = {"chat_id": chat_id}
        if return_bots:
            params["return_bots"] = True
        res = await self._request("getChatAdministrators", **params) or []
        return [ChatMember.from_dict(m) for m in res]

    async def get_chat_member_count(self, chat_id) -> int:
        return await self._request("getChatMemberCount", chat_id=chat_id)

    async def ban_chat_member(self, chat_id, user_id,
                              until_date: Optional[int] = None) -> dict:
        """Ban a member from a chat.

        Note: ``revoke_messages=true`` is not supported yet; the server
        rejects it with ``REVOKE_MESSAGES_UNSUPPORTED``. To delete
        previous messages, call ``delete_message`` for each message id.
        """
        params = {"chat_id": chat_id, "user_id": user_id}
        if until_date:
            params["until_date"] = until_date
        return await self._request("banChatMember", **params)

    async def unban_chat_member(self, chat_id, user_id,
                                only_if_banned: bool = False) -> dict:
        params = {"chat_id": chat_id, "user_id": user_id}
        if only_if_banned:
            params["only_if_banned"] = True
        return await self._request("unbanChatMember", **params)

    async def restrict_chat_member(
        self,
        chat_id,
        user_id,
        permissions,
        use_independent_chat_permissions: bool = False,
        until_date: Optional[int] = None,
    ) -> dict:
        params = {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": _to_dict(permissions),
        }
        if use_independent_chat_permissions:
            params["use_independent_chat_permissions"] = True
        if until_date:
            params["until_date"] = until_date
        return await self._request("restrictChatMember", **params)

    async def set_chat_permissions(
        self,
        chat_id,
        permissions,
        use_independent_chat_permissions: bool = False,
    ) -> dict:
        params = {"chat_id": chat_id, "permissions": _to_dict(permissions)}
        if use_independent_chat_permissions:
            params["use_independent_chat_permissions"] = True
        return await self._request("setChatPermissions", **params)

    async def leave_chat(self, chat_id) -> dict:
        return await self._request("leaveChat", chat_id=chat_id)

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------
    async def send_message(self, chat_id: int, text: str,
                           reply_to_message_id: Optional[int] = None,
                           reply_markup: Optional[InlineKeyboardMarkup] = None,
                           **kwargs) -> dict:
        params = {"chat_id": chat_id, "text": text, **kwargs}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("sendMessage", **params)

    async def send_rich_message(self, chat_id: int, text: str,
                                reply_to_message_id: Optional[int] = None,
                                reply_markup: Optional[InlineKeyboardMarkup] = None,
                                **kwargs) -> dict:
        params = {"chat_id": chat_id, "text": text, **kwargs}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("sendRichMessage", **params)

    async def send_photo(self, chat_id: int, photo_path: str,
                         caption: Optional[str] = None,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
        return await self._send_file(
            "sendPhoto", "photo", chat_id, photo_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_live_photo(self, chat_id: int, photo_path: str,
                              caption: Optional[str] = None,
                              reply_to_message_id: Optional[int] = None,
                              **kwargs) -> dict:
        return await self._send_file(
            "sendLivePhoto", "photo", chat_id, photo_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_document(self, chat_id: int, document_path: str,
                            caption: Optional[str] = None,
                            reply_to_message_id: Optional[int] = None,
                            **kwargs) -> dict:
        return await self._send_file(
            "sendDocument", "document", chat_id, document_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_video(self, chat_id: int, video_path: str,
                         caption: Optional[str] = None,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
        return await self._send_file(
            "sendVideo", "video", chat_id, video_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_video_note(self, chat_id: int, video_note_path: str,
                              reply_to_message_id: Optional[int] = None,
                              **kwargs) -> dict:
        return await self._send_file(
            "sendVideoNote", "video_note", chat_id, video_note_path,
            None, reply_to_message_id, **kwargs
        )

    async def send_audio(self, chat_id: int, audio_path: str,
                         caption: Optional[str] = None,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
        return await self._send_file(
            "sendAudio", "audio", chat_id, audio_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_voice(self, chat_id: int, voice_path: str,
                         caption: Optional[str] = None,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
        return await self._send_file(
            "sendVoice", "voice", chat_id, voice_path,
            caption, reply_to_message_id, **kwargs
        )

    async def send_sticker(self, chat_id: int, sticker_path: str,
                           reply_to_message_id: Optional[int] = None,
                           **kwargs) -> dict:
        return await self._send_file(
            "sendSticker", "sticker", chat_id, sticker_path,
            None, reply_to_message_id, **kwargs
        )

    async def send_animation(self, chat_id: int, animation_path: str,
                             caption: Optional[str] = None,
                             reply_to_message_id: Optional[int] = None,
                             **kwargs) -> dict:
        return await self._send_file(
            "sendAnimation", "animation", chat_id, animation_path,
            caption, reply_to_message_id, **kwargs
        )

    # ------------------------------------------------------------------
    # Locations and contacts
    # ------------------------------------------------------------------
    async def send_location(self, chat_id: int, latitude: float,
                            longitude: float,
                            reply_to_message_id: Optional[int] = None,
                            **kwargs) -> dict:
        params = {
            "chat_id": chat_id,
            "latitude": latitude,
            "longitude": longitude,
            **kwargs,
        }
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
        return await self._request("sendLocation", **params)

    async def send_contact(self, chat_id: int, phone_number: str,
                           first_name: str,
                           last_name: Optional[str] = None,
                           reply_to_message_id: Optional[int] = None,
                           **kwargs) -> dict:
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
        return await self._request("sendContact", **params)

    async def send_venue(self, chat_id: int, latitude: float,
                         longitude: float, title: str, address: str,
                         reply_to_message_id: Optional[int] = None,
                         **kwargs) -> dict:
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
        return await self._request("sendVenue", **params)

    # ------------------------------------------------------------------
    # Editing and deleting
    # ------------------------------------------------------------------
    async def edit_message_text(self, chat_id: int, message_id: int,
                                text: str,
                                reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editMessageText", **params)

    async def edit_message_caption(self, chat_id: int, message_id: int,
                                   caption: str,
                                   reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editMessageCaption", **params)

    async def edit_message_media(self, chat_id: int, message_id: int,
                                 media: dict,
                                 reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "media": _to_dict(media),
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editMessageMedia", **params)

    async def edit_message_reply_markup(self, chat_id: int, message_id: int,
                                        reply_markup: Optional[InlineKeyboardMarkup] = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editMessageReplyMarkup", **params)

    async def delete_message(self, chat_id: int, message_id: int) -> dict:
        return await self._request(
            "deleteMessage", chat_id=chat_id, message_id=message_id
        )

    # ------------------------------------------------------------------
    # Ephemeral messages (Jetra-specific)
    # ------------------------------------------------------------------
    async def edit_ephemeral_message_text(
        self, chat_id: int, message_id: int, text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editEphemeralMessageText", **params)

    async def edit_ephemeral_message_caption(
        self, chat_id: int, message_id: int, caption: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption,
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editEphemeralMessageCaption", **params)

    async def edit_ephemeral_message_media(
        self, chat_id: int, message_id: int, media: dict,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> dict:
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "media": _to_dict(media),
        }
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request("editEphemeralMessageMedia", **params)

    async def edit_ephemeral_message_reply_markup(
        self, chat_id: int, message_id: int,
        reply_markup: Optional[InlineKeyboardMarkup] = None
    ) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup:
            params["reply_markup"] = _to_dict(reply_markup)
        return await self._request(
            "editEphemeralMessageReplyMarkup", **params
        )

    async def delete_ephemeral_message(self, chat_id: int,
                                       message_id: int) -> dict:
        return await self._request(
            "deleteEphemeralMessage",
            chat_id=chat_id,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    async def get_file(self, file_id: str) -> dict:
        return await self._request("getFile", file_id=file_id)

    async def download_file(self, file_id: str, destination_path: str) -> str:
        file_info = await self.get_file(file_id) or {}
        file_path = file_info.get("file_path")
        if not file_path:
            raise JetraError("File path not found.")

        download_url = self.file_url + file_path
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        try:
            async with self._session.get(
                download_url, timeout=120
            ) as response:
                response.raise_for_status()
                with open(destination_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
            return destination_path
        except Exception as e:
            raise JetraError(f"Download failed: {e}")

    # ------------------------------------------------------------------
    # Bot commands and webhook
    # ------------------------------------------------------------------
    async def set_my_commands(self, commands: List[dict]) -> dict:
        return await self._request("setMyCommands", commands=commands)

    async def get_my_commands(self) -> List[dict]:
        return await self._request("getMyCommands")

    async def delete_my_commands(self) -> dict:
        return await self._request("deleteMyCommands")

    async def set_webhook(self, url: str,
                          secret_token: Optional[str] = None,
                          allowed_updates: Optional[List[str]] = None,
                          max_connections: Optional[int] = None,
                          drop_pending_updates: Optional[bool] = None) -> dict:
        params = {"url": url}
        if secret_token:
            params["secret_token"] = secret_token
        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        if max_connections is not None:
            # Bot API allows 1 to 100 concurrent connections.
            if max_connections < 1:
                max_connections = 1
            elif max_connections > 100:
                max_connections = 100
            params["max_connections"] = max_connections
        if drop_pending_updates is not None:
            params["drop_pending_updates"] = drop_pending_updates
        return await self._request("setWebhook", **params)

    async def delete_webhook(self) -> dict:
        return await self._request("deleteWebhook")

    async def get_webhook_info(self) -> dict:
        return await self._request("getWebhookInfo")

    # ------------------------------------------------------------------
    # Menu button and mini-app
    # ------------------------------------------------------------------
    async def set_chat_menu_button(self, chat_id=None,
                                   menu_button=None) -> dict:
        params = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        if menu_button is not None:
            params["menu_button"] = _to_dict(menu_button)
        return await self._request("setChatMenuButton", **params)

    async def get_chat_menu_button(self, chat_id=None) -> dict:
        params = {}
        if chat_id is not None:
            params["chat_id"] = chat_id
        return await self._request("getChatMenuButton", **params)

    async def set_user_emoji_status(
        self,
        user_id: int,
        emoji_status_custom_emoji_id: Optional[str] = None,
        emoji_status_expiration_date: Optional[int] = None,
    ) -> dict:
        params = {"user_id": user_id}
        if emoji_status_custom_emoji_id:
            params["emoji_status_custom_emoji_id"] = (
                emoji_status_custom_emoji_id
            )
        if emoji_status_expiration_date:
            params["emoji_status_expiration_date"] = (
                emoji_status_expiration_date
            )
        return await self._request("setUserEmojiStatus", **params)

    async def answer_web_app_query(self, web_app_query_id: str,
                                   result) -> dict:
        return await self._request(
            "answerWebAppQuery",
            web_app_query_id=web_app_query_id,
            result=_to_dict(result),
        )

    async def save_prepared_inline_message(
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
        return await self._request("savePreparedInlineMessage", **params)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    async def answer_callback_query(self, callback_query_id: str,
                                    text: Optional[str] = None,
                                    show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        if show_alert:
            params["show_alert"] = True
        return await self._request("answerCallbackQuery", **params)

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------
    async def get_updates(self, offset: int = 0,
                          limit: int = 100,
                          timeout: int = 30,
                          allowed_updates: Optional[List[str]] = None) -> List[dict]:
        # Jetra caps long polling at 100 updates and 50 seconds.
        # Clamp values so callers cannot send out-of-range numbers.
        if limit < 1:
            limit = 1
        elif limit > 100:
            limit = 100
        if timeout < 0:
            timeout = 0
        elif timeout > 50:
            timeout = 50

        params = {"offset": offset, "limit": limit, "timeout": timeout}
        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        # Give the HTTP layer a little headroom over the long-poll window.
        http_timeout = max(40, timeout + 10)
        return await self._request("getUpdates", http_timeout=http_timeout, **params)

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
    # Update processing and polling loop
    # ------------------------------------------------------------------
    async def process_update(self, update: dict):
        if "message" in update:
            msg = Message(update["message"], self)
            for handler in self._message_handlers:
                if all(f(msg) for f in handler["filters"]):
                    if asyncio.iscoroutinefunction(handler["func"]):
                        await handler["func"](msg)
                    else:
                        handler["func"](msg)
        elif "edited_message" in update:
            msg = Message(update["edited_message"], self)
            for handler in self._edited_message_handlers:
                if all(f(msg) for f in handler["filters"]):
                    if asyncio.iscoroutinefunction(handler["func"]):
                        await handler["func"](msg)
                    else:
                        handler["func"](msg)
        elif "callback_query" in update:
            cb = CallbackQuery(update["callback_query"], self)
            for handler in self._callback_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(cb)
                else:
                    handler(cb)
        elif "chat_member" in update:
            event = ChatMemberUpdated(update["chat_member"], self)
            for handler in self._chat_member_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
        elif "my_chat_member" in update:
            event = ChatMemberUpdated(update["my_chat_member"], self)
            for handler in self._my_chat_member_handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)

    async def start_polling(self, allowed_updates: Optional[List[str]] = None):
        print("Bot is polling (Async)...")
        offset = 0
        try:
            while True:
                try:
                    updates = await self.get_updates(
                        offset, allowed_updates=allowed_updates
                    )
                    for update in updates:
                        offset = update["update_id"] + 1
                        await self.process_update(update)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[Polling Error] {e}")
                    await asyncio.sleep(2)
        finally:
            await self.close()