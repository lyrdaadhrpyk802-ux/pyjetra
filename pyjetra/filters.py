class Filter:
    def __call__(self, message): return True

class CommandFilter(Filter):
    def __init__(self, commands):
        self.commands = commands if isinstance(commands, list) else [commands]
    def __call__(self, message):
        if not message.text: return False
        cmd = message.text.split()[0].lower()
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
