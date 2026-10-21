# [EN] Terminal Banner for PyJetra
# [FA] بنر ترمینال برای PyJetra
import sys
import os

def print_banner():
    # Only print if running in an interactive terminal (not piped or in logs)
    if not sys.stdout.isatty():
        return

    # ANSI Color Codes
    C_PURPLE = "\033[95m"
    C_CYAN = "\033[96m"
    C_GREEN = "\033[92m"
    C_YELLOW = "\033[93m"
    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"

    # ASCII Art Logo
    logo = f"""
{C_PURPLE}{C_BOLD}    ____       _ ______ _____ _____          
{C_PURPLE}{C_BOLD}   |  _ \     | |  ____|_   _|  __ \   /\    
{C_PURPLE}{C_BOLD}   | |_) |_  _| | |__    | | | |__) | /  \   
{C_PURPLE}{C_BOLD}   |  __/| |/ /| |  __|   | | |  _  / / /\ \  
{C_PURPLE}{C_BOLD}   | |   |   < | | |____  | | | | \ \/ ____ \ 
{C_PURPLE}{C_BOLD}   |_|   |_|\_\|_|______| |_| |_|  \_\_/    \_\
    """

    info = f"""{C_CYAN}   --------------------------------------------------
{C_YELLOW}   Version   : {C_GREEN}v1.3.0
{C_YELLOW}   Developer : {C_GREEN}Ali VEX
{C_YELLOW}   GitHub    : {C_GREEN}https://github.com/lyrdaadhrpyk802-ux
{C_YELLOW}   PyPI      : {C_GREEN}https://pypi.org/project/pyjetra/
{C_CYAN}   --------------------------------------------------{C_RESET}
    """
    
    print(logo + info)

# Automatically run when imported
print_banner()
