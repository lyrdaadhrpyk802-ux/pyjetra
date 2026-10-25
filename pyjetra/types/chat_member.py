# [EN] ChatMember and ChatMemberUpdated types for the Jetra Bot API.

from dataclasses import dataclass, field
from typing import Optional

from .user import User
from .chat import Chat


@dataclass
class ChatMember:
    """Represents a chat member.

    The ``status`` field can be one of:
    ``creator``, ``administrator``, ``member``, ``restricted``,
    ``left``, ``kicked``.
    """

    status: str
    user: User
    raw: dict = field(default_factory=dict)

    # Common fields
    until_date: Optional[int] = None
    is_member: Optional[bool] = None
    is_anonymous: Optional[bool] = None
    custom_title: Optional[str] = None

    # Administrator / creator fields
    can_be_edited: Optional[bool] = None
    can_manage_chat: Optional[bool] = None
    can_delete_messages: Optional[bool] = None
    can_manage_video_chats: Optional[bool] = None
    can_restrict_members: Optional[bool] = None
    can_promote_members: Optional[bool] = None
    can_change_info: Optional[bool] = None
    can_invite_users: Optional[bool] = None
    can_post_messages: Optional[bool] = None
    can_edit_messages: Optional[bool] = None
    can_pin_messages: Optional[bool] = None
    can_manage_topics: Optional[bool] = None

    # Restricted member fields
    can_send_messages: Optional[bool] = None
    can_send_audios: Optional[bool] = None
    can_send_documents: Optional[bool] = None
    can_send_photos: Optional[bool] = None
    can_send_videos: Optional[bool] = None
    can_send_video_notes: Optional[bool] = None
    can_send_voice_notes: Optional[bool] = None
    can_send_polls: Optional[bool] = None
    can_send_other_messages: Optional[bool] = None
    can_add_web_page_previews: Optional[bool] = None
    can_react_to_messages: Optional[bool] = None
    can_edit_tag: Optional[bool] = None

    # Jetra-specific extension fields
    can_send_stickers: Optional[bool] = None
    can_send_gifs: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMember":
        """Build a ChatMember instance from a raw API dict."""
        u = data.get("user") or {}
        user = User(
            id=u.get("id", 0),
            is_bot=u.get("is_bot", False),
            first_name=u.get("first_name", ""),
            last_name=u.get("last_name"),
            username=u.get("username"),
        )
        return cls(
            status=data.get("status", "unknown"),
            user=user,
            raw=data,
            until_date=data.get("until_date"),
            is_member=data.get("is_member"),
            is_anonymous=data.get("is_anonymous"),
            custom_title=data.get("custom_title"),
            can_be_edited=data.get("can_be_edited"),
            can_manage_chat=data.get("can_manage_chat"),
            can_delete_messages=data.get("can_delete_messages"),
            can_manage_video_chats=data.get("can_manage_video_chats"),
            can_restrict_members=data.get("can_restrict_members"),
            can_promote_members=data.get("can_promote_members"),
            can_change_info=data.get("can_change_info"),
            can_invite_users=data.get("can_invite_users"),
            can_post_messages=data.get("can_post_messages"),
            can_edit_messages=data.get("can_edit_messages"),
            can_pin_messages=data.get("can_pin_messages"),
            can_manage_topics=data.get("can_manage_topics"),
            can_send_messages=data.get("can_send_messages"),
            can_send_audios=data.get("can_send_audios"),
            can_send_documents=data.get("can_send_documents"),
            can_send_photos=data.get("can_send_photos"),
            can_send_videos=data.get("can_send_videos"),
            can_send_video_notes=data.get("can_send_video_notes"),
            can_send_voice_notes=data.get("can_send_voice_notes"),
            can_send_polls=data.get("can_send_polls"),
            can_send_other_messages=data.get("can_send_other_messages"),
            can_add_web_page_previews=data.get("can_add_web_page_previews"),
            can_react_to_messages=data.get("can_react_to_messages"),
            can_edit_tag=data.get("can_edit_tag"),
            can_send_stickers=data.get("can_send_stickers"),
            can_send_gifs=data.get("can_send_gifs"),
        )


class ChatMemberUpdated:
    """Represents a ``chat_member`` or ``my_chat_member`` update."""

    def __init__(self, data: dict, bot_instance=None):
        self._bot = bot_instance
        self.raw = data

        chat_data = data.get("chat", {}) or {}
        self.chat = Chat(
            id=chat_data.get("id", 0),
            type=chat_data.get("type", "private"),
            title=chat_data.get("title"),
            first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"),
            username=chat_data.get("username"),
        )

        f = data.get("from", {}) or {}
        self.from_user = User(
            id=f.get("id", 0),
            is_bot=f.get("is_bot", False),
            first_name=f.get("first_name", ""),
            last_name=f.get("last_name"),
            username=f.get("username"),
        )

        self.date = data.get("date")
        self.old_chat_member = ChatMember.from_dict(
            data.get("old_chat_member", {}) or {}
        )
        self.new_chat_member = ChatMember.from_dict(
            data.get("new_chat_member", {}) or {}
        )
        self.invite_link = data.get("invite_link")
        self.via_join_request = data.get("via_join_request")
        self.via_chat_folder_invite_link = data.get(
            "via_chat_folder_invite_link"
        )
