# ============================================
#  pyjetra/userapi/config.py - default data paths for the user account client
#  All code and comments are English. No emojis.
# ============================================
import os

# Session and local database live outside the package so they are never
# shipped with the library. Override with the PYJETRA_DATA_DIR variable.
BASE_DIR = os.path.expanduser("~")
DATA_DIR = os.environ.get("PYJETRA_DATA_DIR") or os.path.join(BASE_DIR, ".pyjetra")

DEFAULT_SESSION_FILE = os.path.join(DATA_DIR, "jetra_session.json")
DEFAULT_DB_FILE = os.path.join(DATA_DIR, "jetra_local.db")
DEFAULT_GROUPS_FILE = os.path.join(DATA_DIR, "groups_only.json")

try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError as e:
    print(f"[config] error: could not create {DATA_DIR}: {e}")
