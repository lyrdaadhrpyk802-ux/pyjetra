# [EN] Message type for PyJetra.
# [FA] Message type for PyJetra.

from typing import Optional, List, Dict, Any, TYPE_CHECKING

from .user import User
from .chat import Chat

if TYPE_CHECKING:
    from ..client import JetraBot
    from .markup import InlineKeyboardMarkup


class Message:
    """Represents a message received from a Jetra chat."""

    def __init__(self, data: dict, bot_instance):
        self._bot = bot_instance
        self.raw = data

        self.message_id = data.get("message_id")
        self.message_thread_id = data.get("message_thread_id")

        chat_data = data.get("chat", {}) or {}
        self.chat = Chat(
            id=chat_data.get("id", 0),
            type=chat_data.get("type", "private"),
            title=chat_data.get("title"),
            first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"),
            username=chat_data.get("username"),
        )

        user_data = data.get("from")
        if user_data:
            self.from_user = User(
                id=user_data.get("id", 0),
                is_bot=user_data.get("is_bot", False),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name"),
                username=user_data.get("username"),
            )
        else:
            self.from_user = None

        self.text = data.get("text")
        self.caption = data.get("caption")
        self.entities = data.get("entities")
        self.caption_entities = data.get("caption_entities")

        self.date = data.get("date")
        self.edit_date = data.get("edit_date")

        reply_data = data.get("reply_to_message")
        if reply_data:
            self.reply_to_message = Message(reply_data, bot_instance)
        else:
            self.reply_to_message = None

        self.forward_from = data.get("forward_from")
        self.forward_from_chat = data.get("forward_from_chat")
        self.forward_date = data.get("forward_date")
        self.forward_sender_name = data.get("forward_sender_name")

        self.document = data.get("document")
        self.photo = data.get("photo")
        self.video = data.get("video")
        self.audio = data.get("audio")
        self.voice = data.get("voice")
        self.sticker = data.get("sticker")
        self.animation = data.get("animation")
        self.video_note = data.get("video_note")
        self.live_photo = data.get("live_photo")

        self.location = data.get("location")
        self.contact = data.get("contact")
        self.venue = data.get("venue")

        self.new_chat_members = data.get("new_chat_members")
        self.left_chat_member = data.get("left_chat_member")
        self.pinned_message = data.get("pinned_message")

    @property
    def is_command(self):
        return bool(self.text and self.text.startswith("/"))

    @property
    def has_media(self):
        return any([
            self.document, self.photo, self.video, self.audio,
            self.voice, self.sticker, self.animation, self.video_note,
            self.live_photo, self.location, self.contact, self.venue,
        ])

    @property
    def command(self):
        if not self.is_command:
            return None
        first_token = self.text.split()[0]
        return first_token[1:].split("@")[0].lower()

    def reply(self, text, reply_markup=None):
        return self._bot.send_message(
            self.chat.id,
            text,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
        )

    def delete(self):
        return self._bot.delete_message(self.chat.id, self.message_id)

    def edit(self, text, reply_markup=None):
        return self._bot.edit_message_text(
            self.chat.id,
            self.message_id,
            text,
            reply_markup=reply_markup,
        )
