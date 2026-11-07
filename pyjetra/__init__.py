# ============================================
#  pyjetra/__init__.py - merged package entry point
#  All code and comments are English. No emojis.
# ============================================
__version__ = "2.0.0.dev0"

# Subpackages are imported explicitly to avoid loading
# both dependency trees at once:
#   from pyjetra.botapi import JetraBot
#   from pyjetra.userapi import JetraClient
