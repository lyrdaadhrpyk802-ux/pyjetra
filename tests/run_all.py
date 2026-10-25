"""Run all offline tests in the tests/ directory.

Existing live tests (test_sync.py, test_async.py, etc.) are skipped
because they need JETRA_TOKEN and a real network connection.
"""

import importlib
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.stdout.isatty = lambda: False

OFFLINE_TESTS = [
    "tests.test_types",
    "tests.test_chat_member",
    "tests.test_filters",
    "tests.test_message",
    "tests.test_callback",
    "tests.test_handlers",
    "tests.test_fsm",
    "tests.test_errors",
    "tests.test_api_surface",
]


def main():
    total = 0
    failed = 0
    for name in OFFLINE_TESTS:
        print("\n=== " + name + " ===")
        try:
            mod = importlib.import_module(name)
            tests = [
                v for k, v in vars(mod).items()
                if k.startswith("test_") and callable(v)
            ]
            for t in tests:
                try:
                    t()
                    total += 1
                    print("  OK  " + t.__name__)
                except Exception as e:
                    failed += 1
                    print("  FAIL " + t.__name__ + ": " + repr(e))
        except Exception as e:
            failed += 1
            print("  FAIL to import: " + repr(e))

    print("\n" + "=" * 50)
    print("Total: %d passed, %d failed" % (total - failed, failed))
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
