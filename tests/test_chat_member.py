"""Offline tests for ChatMember and ChatMemberUpdated."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import ChatMember, ChatMemberUpdated


def test_chat_member_basic():
    m = ChatMember.from_dict({
        "status": "administrator",
        "user": {"id": 1, "is_bot": False, "first_name": "Ali"},
        "can_pin_messages": True,
    })
    assert m.status == "administrator"
    assert m.user.id == 1
    assert m.user.first_name == "Ali"
    assert m.can_pin_messages is True


def test_chat_member_restricted():
    m = ChatMember.from_dict({
        "status": "restricted",
        "user": {"id": 2, "first_name": "X"},
        "until_date": 1700000000,
        "can_send_messages": False,
        "can_send_stickers": False,
        "can_send_gifs": False,
    })
    assert m.status == "restricted"
    assert m.until_date == 1700000000
    assert m.can_send_messages is False
    assert m.can_send_stickers is False
    assert m.can_send_gifs is False


def test_chat_member_creator():
    m = ChatMember.from_dict({
        "status": "creator",
        "user": {"id": 3, "first_name": "Owner"},
        "is_anonymous": False,
        "custom_title": "Founder",
    })
    assert m.status == "creator"
    assert m.is_anonymous is False
    assert m.custom_title == "Founder"


def test_chat_member_unknown_status():
    m = ChatMember.from_dict({"user": {"id": 5, "first_name": "X"}})
    assert m.status == "unknown"
    assert m.user.id == 5


def test_chat_member_empty():
    m = ChatMember.from_dict({})
    assert m.status == "unknown"
    assert m.user.id == 0
    assert m.user.first_name == ""


def test_chat_member_all_admin_fields():
    m = ChatMember.from_dict({
        "status": "administrator",
        "user": {"id": 1, "first_name": "A"},
        "can_be_edited": True,
        "can_manage_chat": True,
        "can_delete_messages": True,
        "can_manage_video_chats": True,
        "can_restrict_members": True,
        "can_promote_members": True,
        "can_change_info": True,
        "can_invite_users": True,
        "can_post_messages": True,
        "can_edit_messages": True,
        "can_pin_messages": True,
        "can_manage_topics": True,
    })
    assert m.can_be_edited is True
    assert m.can_promote_members is True
    assert m.can_manage_topics is True


def test_chat_member_updated():
    ev = ChatMemberUpdated({
        "chat": {"id": -100123, "type": "supergroup", "title": "T"},
        "from": {"id": 1, "first_name": "Ali"},
        "date": 1700000000,
        "old_chat_member": {
            "status": "left",
            "user": {"id": 2, "first_name": "B"},
        },
        "new_chat_member": {
            "status": "member",
            "user": {"id": 2, "first_name": "B"},
        },
    })
    assert ev.chat.id == -100123
    assert ev.chat.title == "T"
    assert ev.from_user.id == 1
    assert ev.date == 1700000000
    assert ev.old_chat_member.status == "left"
    assert ev.new_chat_member.status == "member"


def test_chat_member_updated_my():
    ev = ChatMemberUpdated({
        "chat": {"id": -100, "type": "supergroup"},
        "from": {"id": 1, "first_name": "A"},
        "date": 1,
        "old_chat_member": {
            "status": "member",
            "user": {"id": 9, "is_bot": True, "first_name": "Bot"},
        },
        "new_chat_member": {
            "status": "administrator",
            "user": {"id": 9, "is_bot": True, "first_name": "Bot"},
        },
    })
    assert ev.new_chat_member.status == "administrator"
    assert ev.new_chat_member.user.is_bot is True


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
