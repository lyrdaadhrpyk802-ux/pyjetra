# [EN] Message type for PyJetra.
# [FA] Message type for PyJetra.

from typing import Optional, List, Dict, Any, TYPE_CHECKING

from .user import User
from .chat import Chat

if TYPE_CHECKING:
    from ..client import JetraBot
    from .markup import InlineKeyboardMarkup


class Message:
    """Represents a message received from a Jetra chat.

    Notes from the Jetra Bot API docs:

    - ``new_chat_members`` is a legacy service field. Do not rely on
      it to detect joins. Use ``chat_member`` / ``my_chat_member``
      updates instead, checking the transition from ``left`` or
      ``kicked`` to ``member`` or ``restricted``.
    - ``reply_to_message.from_user`` is only populated when the parent
      message still exists and is visible to the bot.
    """

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

        # Legacy service field. Kept for compatibility, but the Jetra
        # docs recommend using chat_member updates for join detection.
        self.new_chat_members = data.get("new_chat_members")
        self.left_chat_member = data.get("left_chat_member")
        self.pinned_message = data.get("pinned_message")

    # ------------------------------------------------------------------
    # Simple properties
    # ------------------------------------------------------------------
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

    @property
    def is_reply(self) -> bool:
        return self.reply_to_message is not None

    @property
    def is_forwarded(self) -> bool:
        return bool(
            self.forward_from
            or self.forward_from_chat
            or self.forward_sender_name
        )

    @property
    def is_edited(self) -> bool:
        return self.edit_date is not None

    @property
    def photo_file_id(self) -> Optional[str]:
        # Jetra sends photo as a list of sizes; the last one is the largest.
        if not self.photo:
            return None
        if isinstance(self.photo, list) and self.photo:
            return self.photo[-1].get("file_id")
        if isinstance(self.photo, dict):
            return self.photo.get("file_id")
        return None

    @property
    def document_file_id(self) -> Optional[str]:
        if isinstance(self.document, dict):
            return self.document.get("file_id")
        return None

    @property
    def mentions(self) -> List[User]:
        # Entity-based mentions require text. Best-effort only.
        if not self.text or not self.entities:
            return []
        users = []
        for ent in self.entities:
            if ent.get("type") == "text_mention":
                u = ent.get("user") or {}
                users.append(User(
                    id=u.get("id", 0),
                    is_bot=u.get("is_bot", False),
                    first_name=u.get("first_name", ""),
                    last_name=u.get("last_name"),
                    username=u.get("username"),
                ))
        return users

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def reply(self, text, reply_markup=None, **kwargs):
        return self._bot.send_message(
            self.chat.id,
            text,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_photo(self, photo_path, caption=None, reply_markup=None,
                    **kwargs):
        return self._bot.send_photo(
            self.chat.id,
            photo_path,
            caption=caption,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_document(self, document_path, caption=None, reply_markup=None,
                       **kwargs):
        return self._bot.send_document(
            self.chat.id,
            document_path,
            caption=caption,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_video(self, video_path, caption=None, reply_markup=None,
                    **kwargs):
        return self._bot.send_video(
            self.chat.id,
            video_path,
            caption=caption,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_audio(self, audio_path, caption=None, reply_markup=None,
                    **kwargs):
        return self._bot.send_audio(
            self.chat.id,
            audio_path,
            caption=caption,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_voice(self, voice_path, caption=None, reply_markup=None,
                    **kwargs):
        return self._bot.send_voice(
            self.chat.id,
            voice_path,
            caption=caption,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_sticker(self, sticker_path, reply_markup=None, **kwargs):
        return self._bot.send_sticker(
            self.chat.id,
            sticker_path,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_location(self, latitude, longitude, reply_markup=None,
                       **kwargs):
        return self._bot.send_location(
            self.chat.id,
            latitude,
            longitude,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
        )

    def reply_contact(self, phone_number, first_name, last_name=None,
                      reply_markup=None, **kwargs):
        return self._bot.send_contact(
            self.chat.id,
            phone_number,
            first_name,
            last_name=last_name,
            reply_to_message_id=self.message_id,
            reply_markup=reply_markup,
            **kwargs,
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