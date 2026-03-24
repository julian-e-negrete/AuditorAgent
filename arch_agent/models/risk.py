from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RiskCategory(str, Enum):
    SPOF = "SPOF"
    security_gap = "security_gap"
    missing_redundancy = "missing_redundancy"
    tech_debt = "tech_debt"
    undocumented_component = "undocumented_component"
    cross_server_coupling = "cross_server_coupling"
    data_loss_exposure = "data_loss_exposure"


@dataclass
class RiskFinding:
    id: str  # e.g. "RISK-001"
    category: RiskCategory
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    description: str
    affected_components: list[str]
    recommendation: str
    glpi_ticket_id: int | None = None


@dataclass
class RiskReport:
    findings: list[RiskFinding]
    summary: str
    generated_at: datetime = field(default_factory=_now)
