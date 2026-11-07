class Filter:
    def __call__(self, message): return True

class CommandFilter(Filter):
    def __init__(self, commands):
        self.commands = commands if isinstance(commands, list) else [commands]
    def __call__(self, message):
        if not message.text: return False
        # Split by space and get the command part (e.g. /start@Bot)
        parts = message.text.strip().split()
        if not parts: return False
        cmd = parts[0].lower()
        # Remove the @BotName mention if it exists
        if "@" in cmd:
            cmd = cmd.split("@")[0]
        return cmd in [f"/{c}" for c in self.commands]

class TextFilter(Filter):
    def __init__(self, text):
        self.text = text
    def __call__(self, message):
        return bool(message.text and message.text.lower() == self.text.lower())

import re

class RegexFilter(Filter):
    # [EN] Filters messages using a regular expression pattern.
    # [FA] Filters messages using a regular expression pattern.
    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)
    def __call__(self, message):
        return bool(message.text and self.pattern.search(message.text))


class KeywordFilter(Filter):
    """Match the first word of a message (no slash) against keywords.

    Unlike CommandFilter, this works for bare words such as "فعال" or "لغو"
    that Jetra clients do not mark as commands.
    """

    def __init__(self, keywords):
        if isinstance(keywords, str):
            self.keywords = {keywords.lower()}
        else:
            self.keywords = {k.lower() for k in keywords}

    def __call__(self, message):
        if not message.text:
            return False
        first = message.text.strip().split()[0].lower()
        return first in self.keywords
