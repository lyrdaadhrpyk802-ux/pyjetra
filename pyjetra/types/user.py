from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None