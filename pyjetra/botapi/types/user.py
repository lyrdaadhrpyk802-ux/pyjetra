from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

    @property
    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.full_name