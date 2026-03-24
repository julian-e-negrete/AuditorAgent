from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Role = Literal["user", "assistant"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Message:
    role: Role
    content: str
    created_at: datetime = field(default_factory=_now)
