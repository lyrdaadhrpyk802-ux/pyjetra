from typing import Optional, TYPE_CHECKING
from .user import User
from .chat import Chat

class Message:
    def __init__(self, data: dict, bot_instance):
        self.message_id = data.get("message_id")
        chat_data = data.get("chat", {})
        self.chat = Chat(
            id=chat_data.get("id", 0), type=chat_data.get("type", "private"),
            title=chat_data.get("title"), first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"), username=chat_data.get("username")
        )
        self.text = data.get("text")
        self.caption = data.get("caption")
        self.raw = data
        self._bot = bot_instance
        
        user_data = data.get("from")
        if user_data:
            self.from_user = User(
                id=user_data.get("id", 0), is_bot=user_data.get("is_bot", False),
                first_name=user_data.get("first_name", ""), last_name=user_data.get("last_name"),
                username=user_data.get("username")
            )
        else:
            self.from_user = None

    def reply(self, text: str, reply_markup: Optional['InlineKeyboardMarkup'] = None):
        return self._bot.send_message(self.chat.id, text, reply_to_message_id=self.message_id, reply_markup=reply_markup)