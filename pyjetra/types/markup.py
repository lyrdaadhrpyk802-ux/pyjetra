from typing import List, Optional

class InlineKeyboardButton:
    def __init__(self, text: str, callback_data: Optional[str] = None, url: Optional[str] = None):
        self.text = text
        self.callback_data = callback_data
        self.url = url
    def to_dict(self) -> dict:
        data = {"text": self.text}
        if self.callback_data: data["callback_data"] = self.callback_data
        if self.url: data["url"] = self.url
        return data

class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard: List[List[InlineKeyboardButton]]):
        self.inline_keyboard = inline_keyboard
    def to_dict(self) -> dict:
        return {"inline_keyboard": [[btn.to_dict() for btn in row] for row in self.inline_keyboard]}