# ============================================
#  jetrauserapi/logger.py - Centralized logging
#  All code and comments are English. No emojis.
# ============================================

import logging
import os

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LEVEL = "INFO"

_configured = False


def get_logger(name: str = "jetrauserapi") -> logging.Logger:
    """Return a configured logger. Safe to call multiple times."""
    global _configured
    logger = logging.getLogger(name)
    if _configured:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root = logging.getLogger("jetrauserapi")
    root.addHandler(handler)
    level_name = os.getenv("JETRA_LOG_LEVEL", DEFAULT_LEVEL).upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    root.propagate = False
    _configured = True
    return logger
