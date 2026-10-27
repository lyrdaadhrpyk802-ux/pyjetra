"""Offline tests for clamping and upload limits."""

import asyncio
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import JetraBot, AsyncJetraBot
from pyjetra.client import MAX_UPLOAD_BYTES as SYNC_MAX
from pyjetra.async_client import MAX_UPLOAD_BYTES as ASYNC_MAX


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.last_json = None
        self.last_kwargs = None

    def post(self, url, json=None, data=None, files=None, timeout=None):
        self.last_json = json
        self.last_kwargs = {"timeout": timeout}
        return FakeResponse({"ok": True, "result": []})


def _sync_bot_with_fake_session():
    bot = JetraBot("dummy")
    fake = FakeSession()
    bot.session = fake
    return bot, fake


def test_sync_get_updates_defaults():
    bot, fake = _sync_bot_with_fake_session()
    bot.get_updates()
    assert fake.last_json["limit"] == 100
    assert fake.last_json["timeout"] == 30
    assert fake.last_json["offset"] == 0


def test_sync_get_updates_clamps_high():
    bot, fake = _sync_bot_with_fake_session()
    bot.get_updates(limit=500, timeout=120)
    assert fake.last_json["limit"] == 100
    assert fake.last_json["timeout"] == 50


def test_sync_get_updates_clamps_low():
    bot, fake = _sync_bot_with_fake_session()
    bot.get_updates(limit=0, timeout=-5)
    assert fake.last_json["limit"] == 1
    assert fake.last_json["timeout"] == 0


def test_sync_get_updates_http_timeout():
    bot, fake = _sync_bot_with_fake_session()
    bot.get_updates(timeout=50)
    assert fake.last_kwargs["timeout"] == 60
    bot.get_updates(timeout=0)
    assert fake.last_kwargs["timeout"] == 40


def test_sync_set_webhook_max_connections_clamp():
    bot, fake = _sync_bot_with_fake_session()
    bot.set_webhook("https://x.test/hook", max_connections=500)
    assert fake.last_json["max_connections"] == 100
    bot.set_webhook("https://x.test/hook", max_connections=0)
    assert fake.last_json["max_connections"] == 1


def test_sync_set_webhook_drop_pending_false():
    bot, fake = _sync_bot_with_fake_session()
    bot.set_webhook("https://x.test/hook", drop_pending_updates=False)
    assert fake.last_json["drop_pending_updates"] is False


def test_sync_set_webhook_drop_pending_omitted():
    bot, fake = _sync_bot_with_fake_session()
    bot.set_webhook("https://x.test/hook")
    assert "drop_pending_updates" not in fake.last_json


def test_sync_send_file_too_large_raises():
    bot, _ = _sync_bot_with_fake_session()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(b"\0" * (SYNC_MAX + 1))
        path = f.name
    try:
        try:
            bot.send_document(chat_id=1, document_path=path)
            assert False, "Expected FileTooLargeError"
        except Exception as e:
            assert type(e).__name__ == "FileTooLargeError"
    finally:
        os.unlink(path)


def test_sync_send_file_missing_raises():
    bot, _ = _sync_bot_with_fake_session()
    try:
        bot.send_document(chat_id=1, document_path="/no/such/file.bin")
        assert False, "Expected JetraError"
    except Exception as e:
        assert type(e).__name__ == "JetraError"


def test_max_upload_constants_match():
    assert SYNC_MAX == ASYNC_MAX == 25 * 1024 * 1024


def test_async_get_updates_clamps():
    bot = AsyncJetraBot("dummy")

    captured = {}

    async def fake_request(method, http_timeout=30, **params):
        captured["method"] = method
        captured["http_timeout"] = http_timeout
        captured["params"] = params
        return []

    async def go():
        bot._request = fake_request
        await bot.get_updates(limit=500, timeout=120)
        assert captured["params"]["limit"] == 100
        assert captured["params"]["timeout"] == 50
        assert captured["http_timeout"] == 60

        await bot.get_updates(limit=0, timeout=-5)
        assert captured["params"]["limit"] == 1
        assert captured["params"]["timeout"] == 0
        assert captured["http_timeout"] == 40

    asyncio.run(go())


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()