"""Offline tests for error handling."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.isatty = lambda: False

from pyjetra import JetraError


def test_jetra_error_is_exception():
    assert issubclass(JetraError, Exception)


def test_jetra_error_message():
    e = JetraError("boom")
    assert str(e) == "boom"


def test_jetra_error_catch():
    try:
        raise JetraError("test")
    except JetraError as e:
        assert str(e) == "test"


def test_jetra_error_raise_from():
    try:
        try:
            raise ValueError("orig")
        except ValueError as ve:
            raise JetraError("wrapped") from ve
    except JetraError as e:
        assert str(e) == "wrapped"
        assert isinstance(e.__cause__, ValueError)


def run():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print("OK  " + t.__name__)
    print("\n%d tests passed" % len(tests))


if __name__ == "__main__":
    run()
