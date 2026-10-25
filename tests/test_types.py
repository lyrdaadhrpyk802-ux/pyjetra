"""Offline tests for PyJetra type classes."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import (
    User, Chat, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup,
)


def test_user():
    u = User(id=42, is_bot=False, first_name="Ali")
    assert u.id == 42
    assert u.is_bot is False
    assert u.first_name == "Ali"
    assert u.last_name is None
    assert u.username is None


def test_user_with_optionals():
    u = User(
        id=1, is_bot=True, first_name="Bot",
        last_name="X", username="my_bot",
    )
    assert u.last_name == "X"
    assert u.username == "my_bot"


def test_chat():
    c = Chat(id=-100, type="supergroup", title="Test")
    assert c.id == -100
    assert c.type == "supergroup"
    assert c.title == "Test"


def test_chat_permissions_empty():
    p = ChatPermissions()
    assert p.to_dict() == {}


def test_chat_permissions_partial():
    p = ChatPermissions(can_send_messages=True, can_send_stickers=False)
    d = p.to_dict()
    assert d == {"can_send_messages": True, "can_send_stickers": False}


def test_chat_permissions_all_fields():
    p = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_manage_topics=True,
        can_react_to_messages=True,
        can_edit_tag=True,
        can_send_stickers=True,
        can_send_gifs=True,
    )
    d = p.to_dict()
    assert len(d) == 18
    assert all(v is True for v in d.values())


def test_chat_permissions_repr():
    p = ChatPermissions(can_send_messages=True)
    assert "can_send_messages" in repr(p)


def test_inline_button_callback():
    b = InlineKeyboardButton(text="Click", callback_data="do")
    assert b.to_dict() == {"text": "Click", "callback_data": "do"}


def test_inline_button_url():
    b = InlineKeyboardButton(text="Site", url="https://example.com")
    assert b.to_dict() == {"text": "Site", "url": "https://example.com"}


def test_inline_markup():
    m = InlineKeyboardMarkup([
        [InlineKeyboardButton("A", callback_data="a"),
         InlineKeyboardButton("B", callback_data="b")],
        [InlineKeyboardButton("C", url="https://x")],
    ])
    d = m.to_dict()
    assert "inline_keyboard" in d
    assert len(d["inline_keyboard"]) == 2
    assert len(d["inline_keyboard"][0]) == 2
    assert d["inline_keyboard"][1][0]["url"] == "https://x"


def test_inline_button_no_payload():
    b = InlineKeyboardButton(text="Text only")
    assert b.to_dict() == {"text": "Text only"}


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
