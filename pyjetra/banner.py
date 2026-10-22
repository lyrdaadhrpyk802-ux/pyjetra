# [EN] Terminal banner for PyJetra.
# [FA] Terminal banner for PyJetra.

import sys


def print_banner():
    # Only print if stdout is an interactive terminal (not piped/logged).
    if not sys.stdout.isatty():
        return

    # ANSI color codes
    C_PURPLE = "\033[95m"
    C_CYAN = "\033[96m"
    C_GREEN = "\033[92m"
    C_YELLOW = "\033[93m"
    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"

    # ASCII art uses a raw string so backslashes are literal.
    logo = r"""
    ____       _ ______ _____ _____
   |  _ \     | |  ____|_   _|  __ \   /\
   | |_) |_  _| | |__    | | | |__) | /  \
   |  __/| |/ /| |  __|   | | |  _  / / /\ \
   | |   |   < | | |____  | | | | \ \/ ____ \
   |_|   |_|\_\|_|______| |_| |_|  \_\_/    \_\
"""

    info = (
        f"{C_CYAN}   --------------------------------------------------\n"
        f"{C_YELLOW}   Version   : {C_GREEN}v1.5.0\n"
        f"{C_YELLOW}   Developer : {C_GREEN}Ali VEX\n"
        f"{C_YELLOW}   GitHub    : {C_GREEN}https://github.com/lyrdaadhrpyk802-ux\n"
        f"{C_YELLOW}   PyPI      : {C_GREEN}https://pypi.org/project/pyjetra/\n"
        f"{C_CYAN}   --------------------------------------------------{C_RESET}\n"
    )

    print(C_PURPLE + C_BOLD + logo + C_RESET + info)


print_banner()
