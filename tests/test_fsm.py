"""Offline tests for FSM state management on both clients."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import JetraBot, AsyncJetraBot


def test_sync_fsm_lifecycle():
    bot = JetraBot("dummy")
    assert bot.get_state(1) is None
    bot.set_state(1, "waiting")
    assert bot.get_state(1) == "waiting"
    bot.set_state(1, "other")
    assert bot.get_state(1) == "other"
    bot.clear_state(1)
    assert bot.get_state(1) is None


def test_sync_fsm_multiple_users():
    bot = JetraBot("dummy")
    bot.set_state(1, "a")
    bot.set_state(2, "b")
    assert bot.get_state(1) == "a"
    assert bot.get_state(2) == "b"
    bot.clear_state(1)
    assert bot.get_state(1) is None
    assert bot.get_state(2) == "b"


def test_sync_clear_nonexistent():
    bot = JetraBot("dummy")
    bot.clear_state(999)  # must not raise
    assert bot.get_state(999) is None


def test_async_fsm_lifecycle():
    bot = AsyncJetraBot("dummy")
    assert bot.get_state(1) is None
    bot.set_state(1, "waiting")
    assert bot.get_state(1) == "waiting"
    bot.clear_state(1)
    assert bot.get_state(1) is None


def test_fsm_isolated_per_client():
    b1 = JetraBot("a")
    b2 = JetraBot("b")
    b1.set_state(1, "x")
    assert b2.get_state(1) is None


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
