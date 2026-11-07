from typing import Optional
from .user import User
from .message import Message

class CallbackQuery:
    def __init__(self, data: dict, bot_instance):
        self.id = data.get("id")
        self.from_user = None
        if "from" in data:
            u = data["from"]
            self.from_user = User(
                id=u.get("id", 0), is_bot=u.get("is_bot", False),
                first_name=u.get("first_name", ""), last_name=u.get("last_name"),
                username=u.get("username")
            )
        self.data = data.get("data")
        self.message = Message(data["message"], bot_instance) if "message" in data else None
        self._bot = bot_instance

    def answer(self, text: Optional[str] = None, show_alert: bool = False):
        return self._bot.answer_callback_query(self.id, text, show_alert)