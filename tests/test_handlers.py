"""Offline tests for decorators and process_update on both clients."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import JetraBot, AsyncJetraBot, CommandFilter


def _msg_update(mid=1, text="hi"):
    return {
        "update_id": mid,
        "message": {
            "message_id": mid,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "first_name": "A"},
            "text": text,
            "date": 0,
        },
    }


def _cb_update(cid="cb1"):
    return {
        "update_id": 2,
        "callback_query": {
            "id": cid,
            "from": {"id": 1, "first_name": "A"},
            "data": "x",
        },
    }


def _cm_update():
    return {
        "update_id": 3,
        "chat_member": {
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 1, "first_name": "A"},
            "date": 0,
            "old_chat_member": {"status": "left", "user": {"id": 2, "first_name": "B"}},
            "new_chat_member": {"status": "member", "user": {"id": 2, "first_name": "B"}},
        },
    }


def _mcm_update():
    return {
        "update_id": 4,
        "my_chat_member": {
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 1, "first_name": "A"},
            "date": 0,
            "old_chat_member": {"status": "member", "user": {"id": 9, "is_bot": True, "first_name": "Bot"}},
            "new_chat_member": {"status": "administrator", "user": {"id": 9, "is_bot": True, "first_name": "Bot"}},
        },
    }


def test_sync_all_handlers_fire():
    bot = JetraBot("dummy")
    hits = []

    @bot.on_message()
    def _m(msg):
        hits.append(("m", msg.message_id))

    @bot.on_callback_query()
    def _c(q):
        hits.append(("c", q.id))

    @bot.on_chat_member()
    def _cm(ev):
        hits.append(("cm", ev.new_chat_member.status))

    @bot.on_my_chat_member()
    def _mcm(ev):
        hits.append(("mcm", ev.new_chat_member.status))

    bot.process_update(_msg_update(1))
    bot.process_update(_cb_update("cb1"))
    bot.process_update(_cm_update())
    bot.process_update(_mcm_update())

    assert ("m", 1) in hits
    assert ("c", "cb1") in hits
    assert ("cm", "member") in hits
    assert ("mcm", "administrator") in hits


def test_sync_filter_passes():
    bot = JetraBot("dummy")
    hits = []

    @bot.on_message(filters=[CommandFilter("start")])
    def _h(msg):
        hits.append(msg.text)

    bot.process_update(_msg_update(1, "/start"))
    bot.process_update(_msg_update(2, "not a command"))
    assert hits == ["/start"]


def test_sync_multiple_handlers():
    bot = JetraBot("dummy")
    counter = {"n": 0}

    @bot.on_message()
    def _h1(msg):
        counter["n"] += 1

    @bot.on_message()
    def _h2(msg):
        counter["n"] += 1

    bot.process_update(_msg_update(1))
    assert counter["n"] == 2


def test_async_all_handlers_fire():
    async def go():
        bot = AsyncJetraBot("dummy")
        hits = []

        @bot.on_message()
        async def _m(msg):
            hits.append(("m", msg.message_id))

        @bot.on_callback_query()
        async def _c(q):
            hits.append(("c", q.id))

        @bot.on_chat_member()
        async def _cm(ev):
            hits.append(("cm", ev.new_chat_member.status))

        @bot.on_my_chat_member()
        async def _mcm(ev):
            hits.append(("mcm", ev.new_chat_member.status))

        await bot.process_update(_msg_update(1))
        await bot.process_update(_cb_update("cb1"))
        await bot.process_update(_cm_update())
        await bot.process_update(_mcm_update())

        assert ("m", 1) in hits
        assert ("c", "cb1") in hits
        assert ("cm", "member") in hits
        assert ("mcm", "administrator") in hits

    asyncio.run(go())


def test_async_sync_handler_mix():
    """A sync handler registered on AsyncJetraBot should still run."""
    async def go():
        bot = AsyncJetraBot("dummy")
        hits = []

        @bot.on_message()
        def _sync(msg):
            hits.append("sync")

        @bot.on_message()
        async def _async(msg):
            hits.append("async")

        await bot.process_update(_msg_update(1))
        assert "sync" in hits
        assert "async" in hits

    asyncio.run(go())


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
