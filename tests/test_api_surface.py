"""Ensure every documented Jetra Bot API method exists on both clients."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import JetraBot, AsyncJetraBot


DOCUMENTED_METHODS = [
    # Account
    "get_me",
    # Group and members
    "get_chat",
    "get_chat_member",
    "get_chat_administrators",
    "get_chat_member_count",
    "ban_chat_member",
    "unban_chat_member",
    "restrict_chat_member",
    "set_chat_permissions",
    "leave_chat",
    # Messages
    "send_message",
    "send_rich_message",
    "send_photo",
    "send_live_photo",
    "send_document",
    "send_video",
    "send_video_note",
    "send_audio",
    "send_voice",
    "send_sticker",
    "send_animation",
    "send_location",
    "send_contact",
    "send_venue",
    # Editing / deleting
    "edit_message_text",
    "edit_message_caption",
    "edit_message_media",
    "edit_message_reply_markup",
    "delete_message",
    # Ephemeral
    "edit_ephemeral_message_text",
    "edit_ephemeral_message_caption",
    "edit_ephemeral_message_media",
    "edit_ephemeral_message_reply_markup",
    "delete_ephemeral_message",
    # Files
    "get_file",
    "download_file",
    # Commands
    "set_my_commands",
    "get_my_commands",
    "delete_my_commands",
    # Webhook
    "set_webhook",
    "delete_webhook",
    "get_webhook_info",
    # Menu / mini-app
    "set_chat_menu_button",
    "get_chat_menu_button",
    "set_user_emoji_status",
    "answer_web_app_query",
    "save_prepared_inline_message",
    # Callbacks
    "answer_callback_query",
    # Updates
    "get_updates",
    # Decorators
    "on_message",
    "on_edited_message",
    "on_callback_query",
    "on_chat_member",
    "on_my_chat_member",
    # FSM
    "set_state",
    "get_state",
    "clear_state",
    # Update processing
    "process_update",
]


def _check(cls, name):
    missing = [m for m in DOCUMENTED_METHODS if not hasattr(cls, m)]
    if missing:
        raise AssertionError(
            name + " missing methods:\n  - " + "\n  - ".join(missing)
        )
    return len(DOCUMENTED_METHODS)


def test_sync_surface():
    count = _check(JetraBot, "JetraBot")
    print("JetraBot has all %d documented methods" % count)


def test_async_surface():
    count = _check(AsyncJetraBot, "AsyncJetraBot")
    print("AsyncJetraBot has all %d documented methods" % count)


def test_sync_poll():
    assert hasattr(JetraBot, "poll")


def test_async_poll():
    assert hasattr(AsyncJetraBot, "start_polling")


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
