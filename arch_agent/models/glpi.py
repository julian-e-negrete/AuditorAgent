from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Ticket:
    id: int
    title: str
    content: str
    status: Literal["new", "processing", "pending", "solved", "closed"]
    urgency: int  # 1=very_high ... 5=very_low (matches proxy scale)
    created_at: datetime = field(default_factory=_now)
