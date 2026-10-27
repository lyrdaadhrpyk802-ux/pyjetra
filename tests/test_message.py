"""Offline tests for the Message type parser."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra.types import Message


class FakeBot:
    def send_message(self, chat_id, text, **kwargs):
        return {"chat_id": chat_id, "text": text}

    def delete_message(self, chat_id, message_id):
        return {"chat_id": chat_id, "message_id": message_id}

    def edit_message_text(self, chat_id, message_id, text, **kwargs):
        return {"chat_id": chat_id, "message_id": message_id}


def _msg(data):
    return Message(data, FakeBot())


def _base():
    return {
        "message_id": 1,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "is_bot": False, "first_name": "Ali"},
        "date": 1700000000,
    }


def test_message_basic():
    m = _msg(_base())
    assert m.message_id == 1
    assert m.chat.id == 42
    assert m.from_user.id == 42
    assert m.from_user.first_name == "Ali"
    assert m.text is None


def test_message_text():
    d = _base()
    d["text"] = "hello"
    m = _msg(d)
    assert m.text == "hello"
    assert not m.is_command


def test_message_command():
    d = _base()
    d["text"] = "/start@bot arg"
    m = _msg(d)
    assert m.is_command
    assert m.command == "start"


def test_message_command_simple():
    d = _base()
    d["text"] = "/help"
    m = _msg(d)
    assert m.command == "help"


def test_message_reply():
    d = _base()
    d["text"] = "response"
    d["reply_to_message"] = {
        "message_id": 0,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 99, "first_name": "Bob"},
        "text": "original",
    }
    m = _msg(d)
    assert m.reply_to_message is not None
    assert m.reply_to_message.text == "original"
    assert m.reply_to_message.from_user.id == 99


def test_message_reply_without_from():
    # Per Jetra docs, reply_to_message.from is only present when the
    # parent message is still visible to the bot.
    d = _base()
    d["text"] = "response"
    d["reply_to_message"] = {
        "message_id": 0,
        "chat": {"id": 42, "type": "private"},
        "text": "original",
    }
    m = _msg(d)
    assert m.reply_to_message is not None
    assert m.reply_to_message.from_user is None


def test_message_no_reply():
    m = _msg(_base())
    assert m.reply_to_message is None


def test_message_media_photo():
    d = _base()
    d["photo"] = [{"file_id": "abc"}]
    m = _msg(d)
    assert m.photo == [{"file_id": "abc"}]
    assert m.has_media


def test_message_media_document():
    d = _base()
    d["document"] = {"file_id": "def"}
    m = _msg(d)
    assert m.has_media


def test_message_no_media():
    m = _msg(_base())
    assert not m.has_media


def test_message_location():
    d = _base()
    d["location"] = {"latitude": 35.0, "longitude": 51.0}
    m = _msg(d)
    assert m.location["latitude"] == 35.0
    assert m.has_media


def test_message_forward():
    d = _base()
    d["forward_from"] = {"id": 5, "first_name": "X"}
    d["forward_date"] = 1700000001
    m = _msg(d)
    assert m.forward_from["id"] == 5
    assert m.forward_date == 1700000001


def test_message_reply_call():
    d = _base()
    d["text"] = "hi"
    m = _msg(d)
    result = m.reply("ok")
    assert result["chat_id"] == 42
    assert result["text"] == "ok"


def test_message_delete_call():
    m = _msg(_base())
    result = m.delete()
    assert result["message_id"] == 1


def test_message_edit_call():
    d = _base()
    d["text"] = "old"
    m = _msg(d)
    result = m.edit("new")
    assert result["message_id"] == 1


def test_message_sticker():
    d = _base()
    d["sticker"] = {"file_id": "stk"}
    m = _msg(d)
    assert m.has_media


def test_message_voice():
    d = _base()
    d["voice"] = {"file_id": "v"}
    m = _msg(d)
    assert m.has_media


def test_message_animation():
    d = _base()
    d["animation"] = {"file_id": "a"}
    m = _msg(d)
    assert m.has_media


def test_message_contact():
    d = _base()
    d["contact"] = {"phone_number": "+1"}
    m = _msg(d)
    assert m.has_media


def test_message_venue():
    d = _base()
    d["venue"] = {"title": "Cafe"}
    m = _msg(d)
    assert m.has_media


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()