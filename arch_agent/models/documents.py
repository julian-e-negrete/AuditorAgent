from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DocumentSection:
    heading: str
    content: str
    section_type: Literal["prose", "mermaid", "code", "table"]
    source_file: str


@dataclass
class DocumentContext:
    sections: list[DocumentSection]
    raw_text: str
    source_files: list[str]
    loaded_at: datetime = field(default_factory=_now)
