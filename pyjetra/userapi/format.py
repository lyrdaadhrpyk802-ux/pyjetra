# ============================================
#  jetrauserapi/format.py - Text formatting helpers
#  All code and comments are English. No emojis.
# ============================================

from pyjetra.userapi.message import MessageEntity


# Constructor IDs for message entities (Jetra layer 228).
CTOR_BOLD = 0xBD610BC9
CTOR_ITALIC = 0x826F8B60
CTOR_UNDERLINE = 0x9C4E7E8B
CTOR_STRIKE = 0xBF0693D4
CTOR_CODE = 0x28A20571
CTOR_PRE = 0x73924BE0
CTOR_URL = 0x6ED02538
CTOR_TEXT_URL = 0x76A6D327
CTOR_MENTION = 0xFA04579D
CTOR_HASHTAG = 0x6F635B0D
CTOR_BOT_COMMAND = 0x6CEF8AC7
CTOR_EMAIL = 0x64E475C2
CTOR_PHONE = 0x9B69E34B


class Formatted:
    """
    Mutable text buffer that tracks formatting entities.

    Usage:
        f = Formatted()
        f += "Hello "
        f.add("world", "bold")
        f += "!"

        text = f.text
        entities = f.entities
    """

    def __init__(self):
        self.text = ""
        self.entities = []

    def add(self, text, entity_type, extra=None):
        """Append text with an entity covering exactly this slice."""
        offset = len(self.text)
        self.text += text
        self.entities.append(
            MessageEntity(entity_type, offset, len(text), extra)
        )
        return self

    def __iadd__(self, text):
        if isinstance(text, Formatted):
            offset = len(self.text)
            self.text += text.text
            for e in text.entities:
                self.entities.append(
                    MessageEntity(e.type, e.offset + offset, e.length, e.extra)
                )
        else:
            self.text += str(text)
        return self

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"<Formatted len={len(self.text)} entities={len(self.entities)}>"


def bold(text):
    return Formatted().add(text, "bold")


def italic(text):
    return Formatted().add(text, "italic")


def underline(text):
    return Formatted().add(text, "underline")


def strike(text):
    return Formatted().add(text, "strike")


def code(text):
    return Formatted().add(text, "code")


def pre(text, lang=""):
    return Formatted().add(text, "pre", extra=lang)


def url(text, link):
    """Clickable text that points to a URL."""
    return Formatted().add(text, "text_url", extra=link)


def mention(text):
    return Formatted().add(text, "mention")


def hashtag(text):
    return Formatted().add(text, "hashtag")


def bot_command(text):
    return Formatted().add(text, "bot_command")


def email(text):
    return Formatted().add(text, "email")


def phone(text):
    return Formatted().add(text, "phone")
