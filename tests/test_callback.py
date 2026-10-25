"""Offline tests for CallbackQuery parsing."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra.types import CallbackQuery


class FakeBot:
    def answer_callback_query(self, cid, text=None, alert=False):
        return {"id": cid, "text": text, "alert": alert}


def test_callback_basic():
    cb = CallbackQuery({
        "id": "cb1",
        "from": {"id": 42, "is_bot": False, "first_name": "Ali"},
        "data": "click_me",
    }, FakeBot())
    assert cb.id == "cb1"
    assert cb.from_user.id == 42
    assert cb.data == "click_me"
    assert cb.message is None


def test_callback_with_message():
    cb = CallbackQuery({
        "id": "cb2",
        "from": {"id": 42, "first_name": "Ali"},
        "data": "x",
        "message": {
            "message_id": 100,
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 1, "first_name": "A"},
            "text": "menu",
            "date": 1700000000,
        },
    }, FakeBot())
    assert cb.message is not None
    assert cb.message.message_id == 100
    assert cb.message.text == "menu"


def test_callback_answer():
    bot = FakeBot()
    cb = CallbackQuery({
        "id": "cb3",
        "from": {"id": 1, "first_name": "A"},
        "data": "y",
    }, bot)
    result = cb.answer("thanks")
    assert result["text"] == "thanks"
    assert result["alert"] is False


def test_callback_answer_alert():
    bot = FakeBot()
    cb = CallbackQuery({
        "id": "cb4",
        "from": {"id": 1, "first_name": "A"},
        "data": "z",
    }, bot)
    result = cb.answer("warning", show_alert=True)
    assert result["alert"] is True


def test_callback_no_from():
    cb = CallbackQuery({"id": "cb5", "data": "x"}, FakeBot())
    assert cb.from_user is None


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
