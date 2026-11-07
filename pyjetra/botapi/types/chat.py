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

    @property
    def is_private(self) -> bool:
        return self.type == "private"

    @property
    def is_group(self) -> bool:
        return self.type in ("group", "supergroup")

    @property
    def is_channel(self) -> bool:
        return self.type == "channel"

    @property
    def display_name(self) -> str:
        if self.title:
            return self.title
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name
        return str(self.id)


class ChatPermissions:
    """Represents chat member permissions.

    Jetra-specific extension fields:
    ``can_send_stickers`` and ``can_send_gifs``.

    Any field not provided stays ``None`` and is omitted from the
    serialized dict, so the server keeps its current default.

    Per the Jetra Bot API docs, when ``can_send_stickers`` or
    ``can_send_gifs`` are not explicitly set, they follow
    ``can_send_other_messages``. This fallback is applied in
    ``to_dict`` so callers do not have to repeat it.
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
        data = {
            field: getattr(self, field)
            for field in self._FIELDS
            if getattr(self, field) is not None
        }

        # Jetra-specific fallback: when the two extension fields are
        # not explicitly provided, they inherit can_send_other_messages.
        other = data.get("can_send_other_messages")
        if other is not None:
            data.setdefault("can_send_stickers", other)
            data.setdefault("can_send_gifs", other)

        return data

    # ------------------------------------------------------------------
    # Convenience factories
    # ------------------------------------------------------------------
    @classmethod
    def muted(cls) -> "ChatPermissions":
        """All permissions explicitly disabled."""
        return cls(**{field: False for field in cls._FIELDS})

    @classmethod
    def text_only(cls) -> "ChatPermissions":
        """Allow text messages only; no media, no polls, no previews."""
        data = {field: False for field in cls._FIELDS}
        data["can_send_messages"] = True
        data["can_add_web_page_previews"] = True
        return cls(**data)

    @classmethod
    def media_only(cls) -> "ChatPermissions":
        """Allow media and stickers, but not plain text messages."""
        data = {field: False for field in cls._FIELDS}
        data["can_send_audios"] = True
        data["can_send_documents"] = True
        data["can_send_photos"] = True
        data["can_send_videos"] = True
        data["can_send_video_notes"] = True
        data["can_send_voice_notes"] = True
        data["can_send_other_messages"] = True
        data["can_send_stickers"] = True
        data["can_send_gifs"] = True
        return cls(**data)

    @classmethod
    def everything(cls) -> "ChatPermissions":
        """All permissions explicitly enabled."""
        return cls(**{field: True for field in cls._FIELDS})

    @classmethod
    def from_dict(cls, data: dict) -> "ChatPermissions":
        """Build from a raw dict (e.g. from getChat / getChatMember)."""
        return cls(**(data or {}))

    def __repr__(self) -> str:
        return f"ChatPermissions({self.to_dict()})"