from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BaseDocument:
    content: str
    generated_at: datetime = field(default_factory=_now)


@dataclass
class DesignDecision:
    title: str
    context: str
    decision: str
    rationale: str
    consequences: str
    alternatives_considered: list[str]
    status: Literal["proposed", "accepted", "deprecated", "superseded"]


@dataclass
class ADRDocument(BaseDocument):
    decision: DesignDecision = field(default_factory=lambda: DesignDecision(
        title="", context="", decision="", rationale="",
        consequences="", alternatives_considered=[], status="proposed"
    ))
    adr_number: int = 0
    filename: str = ""  # e.g. "adr-001-redis-cache.md"


@dataclass
class RunbookDocument(BaseDocument):
    scenario: str = ""
    steps: list[str] = field(default_factory=list)


@dataclass
class ArchDocument(BaseDocument):
    title: str = ""
