# [EN] Terminal banner for PyJetra.

import os
import sys
import time

from .dev_info import VERSION


def print_banner():
    """Print an animated single-line PyJetra banner.

    Skipped silently when:
    - PYJETRA_NO_BANNER is set (any non-empty value)
    - stdout is not a TTY (piped output, CI, log files)
    """
    if os.environ.get("PYJETRA_NO_BANNER"):
        return
    if not sys.stdout.isatty():
        return

    GREEN = "\033[92m"
    BRIGHT = "\033[1;92m"
    RESET = "\033[0m"

    prompt = ">> "
    text = f"PyJetra v{VERSION}  |  Ali VEX  |  jetra.ir/UserBoT"
    full = prompt + text

    # If the terminal is too narrow, skip the animation.
    try:
        cols = os.get_terminal_size().columns
    except OSError:
        cols = 80
    if len(full) + 3 > cols:
        print(BRIGHT + prompt + GREEN + text + RESET)
        return

    # 1) Prompt appears immediately.
    sys.stdout.write(BRIGHT + prompt + RESET)
    sys.stdout.flush()

    # 2) Typewriter effect on the body text.
    for char in text:
        sys.stdout.write(GREEN + char + RESET)
        sys.stdout.flush()
        time.sleep(0.012)

    # 3) Brief glow: repaint the full line in bright green.
    time.sleep(0.08)
    sys.stdout.write("\r" + BRIGHT + full + RESET + "   ")
    sys.stdout.flush()
    time.sleep(0.12)

    # 4) Settle back to normal green and finish the line.
    sys.stdout.write("\r" + BRIGHT + prompt + GREEN + text + RESET + "\n")
    sys.stdout.flush()


print_banner()
