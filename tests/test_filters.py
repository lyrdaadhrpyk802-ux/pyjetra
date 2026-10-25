"""Offline tests for filter classes."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import CommandFilter, TextFilter, RegexFilter


class FakeMessage:
    def __init__(self, text=None):
        self.text = text


def test_command_filter_single():
    f = CommandFilter("start")
    assert f(FakeMessage("/start"))
    assert f(FakeMessage("/start arg"))
    assert not f(FakeMessage("/other"))
    assert not f(FakeMessage("no command"))
    assert not f(FakeMessage(None))


def test_command_filter_list():
    f = CommandFilter(["start", "help"])
    assert f(FakeMessage("/start"))
    assert f(FakeMessage("/help"))
    assert not f(FakeMessage("/other"))


def test_command_filter_case_correct():
    f = CommandFilter("start")
    assert f(FakeMessage("/START")) is True
    assert f(FakeMessage("/StArT")) is True


def test_text_filter_exact():
    f = TextFilter("hello")
    assert f(FakeMessage("hello"))
    assert f(FakeMessage("HELLO"))
    assert not f(FakeMessage("hello world"))
    assert not f(FakeMessage(None))


def test_regex_filter():
    f = RegexFilter(r"^\d+$")
    assert f(FakeMessage("12345"))
    assert not f(FakeMessage("12a"))
    assert not f(FakeMessage(None))


def test_regex_filter_search():
    f = RegexFilter(r"hello")
    assert f(FakeMessage("say hello there"))
    assert not f(FakeMessage("say hi there"))


def run():
    tests = [
        test_command_filter_single,
        test_command_filter_list,
        test_command_filter_case_correct,
        test_text_filter_exact,
        test_regex_filter,
        test_regex_filter_search,
    ]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
