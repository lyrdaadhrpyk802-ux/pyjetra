# [EN] Chat and ChatPermissions types for the Jetra Bot API.

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


class ChatPermissions:
    """Represents chat member permissions.

    Jetra-specific extension fields:
    ``can_send_stickers`` and ``can_send_gifs``.

    Any field not provided stays ``None`` and is omitted from the
    serialized dict, so the server keeps its current default.
    """

    _FIELDS = (
        "can_send_messages",
        "can_send_audios",
        "can_send_documents",
        "can_send_photos",
        "can_send_videos",
        "can_send_video_notes",
        "can_send_voice_notes",
        "can_send_polls",
        "can_send_other_messages",
        "can_add_web_page_previews",
        "can_change_info",
        "can_invite_users",
        "can_pin_messages",
        "can_manage_topics",
        "can_react_to_messages",
        "can_edit_tag",
        "can_send_stickers",
        "can_send_gifs",
    )

    def __init__(self, **kwargs):
        for field in self._FIELDS:
            setattr(self, field, kwargs.get(field))

    def to_dict(self) -> dict:
        return {
            field: getattr(self, field)
            for field in self._FIELDS
            if getattr(self, field) is not None
        }

    def __repr__(self) -> str:
        return f"ChatPermissions({self.to_dict()})"
