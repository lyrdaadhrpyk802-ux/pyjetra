import datetime


class MessageEntity:
    """Represents a text formatting entity (bold, italic, link, etc)."""
    def __init__(self, type, offset, length, extra=None):
        self.type = type
        self.offset = offset
        self.length = length
        self.extra = extra

    def __repr__(self):
        return f"<Entity {self.type} offset={self.offset} length={self.length} extra={self.extra}>"


class Message:
    """
    Represents a message in Jetra.
    """
    
    def __init__(self, msg_id, from_id, peer_id, peer_type, date, text, reply_to_msg_id=None, entities=None):
        self.id = msg_id
        self.from_id = from_id
        self.peer_id = peer_id
        self.peer_type = peer_type
        self.date = date
        self.text = text
        self.reply_to_msg_id = reply_to_msg_id
        self.entities = entities or []
    
    @property
    def is_private(self):
        return self.peer_type == 'user'
    
    @property
    def is_group(self):
        return self.peer_type == 'group'

    @property
    def is_reply(self):
        return self.reply_to_msg_id is not None
    
    @property
    def date_str(self):
        try:
            return datetime.datetime.fromtimestamp(self.date).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return str(self.date)
    
    def to_dict(self):
        return {
            'id': self.id,
            'from_id': self.from_id,
            'peer_id': self.peer_id,
            'peer_type': self.peer_type,
            'date': self.date,
            'text': self.text,
            'reply_to_msg_id': self.reply_to_msg_id,
            'entities': [str(e) for e in self.entities]
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            msg_id=data['id'],
            from_id=data['from_id'],
            peer_id=data['peer_id'],
            peer_type=data['peer_type'],
            date=data['date'],
            text=data['text'],
            reply_to_msg_id=data.get('reply_to_msg_id'),
            entities=None
        )
    
    def parse_entities(self):
        """Return list of (type, text_slice, extra) tuples."""
        result = []
        for e in self.entities:
            piece = self.text[e.offset:e.offset + e.length]
            result.append((e.type, piece, e.extra))
        return result

    def to_markdown(self):
        """Convert message text with entities to Markdown."""
        if not self.entities:
            return self.text

        # Sort by offset descending so replacing doesn't shift positions
        entities_sorted = sorted(self.entities, key=lambda e: e.offset, reverse=True)
        text = self.text
        for e in entities_sorted:
            start = e.offset
            end = start + e.length
            piece = text[start:end]
            if e.type == "bold":
                text = text[:start] + "**" + piece + "**" + text[end:]
            elif e.type == "italic":
                text = text[:start] + "_" + piece + "_" + text[end:]
            elif e.type == "underline":
                text = text[:start] + "__" + piece + "__" + text[end:]
            elif e.type == "strike":
                text = text[:start] + "~~" + piece + "~~" + text[end:]
            elif e.type == "code":
                text = text[:start] + "`" + piece + "`" + text[end:]
            elif e.type == "pre":
                lang = e.extra or ""
                text = text[:start] + "```" + lang + "\n" + piece + "\n```" + text[end:]
            elif e.type in ("text_url", "url"):
                url = e.extra or piece
                text = text[:start] + "[" + piece + "](" + url + ")" + text[end:]
        return text

    def __repr__(self):
        reply_str = f" (reply to {self.reply_to_msg_id})" if self.is_reply else ""
        ent_str = f" [{len(self.entities)} entities]" if self.entities else ""
        return f"<Message id={self.id} from={self.from_id} peer={self.peer_id} ({self.peer_type}){reply_str}{ent_str} text='{self.text[:30]}'>"
