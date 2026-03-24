"""RiskAnalysisTool — uses the LLM to identify architectural risks from a DocumentContext."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import litellm

from arch_agent.config import Settings
from arch_agent.exceptions import LLMUnavailableError
from arch_agent.models.documents import DocumentContext
from arch_agent.models.risk import RiskCategory, RiskFinding, RiskReport


def _now() -> datetime:
    return datetime.now(timezone.utc)


_SYSTEM_PROMPT = """\
You are a senior system architect performing an architectural risk analysis.
Analyze the provided architecture documentation and identify risks across these 7 categories:
- SPOF (single points of failure)
- security_gap (missing authentication, authorization, encryption, etc.)
- missing_redundancy (no failover, no replication, no backup)
- tech_debt (outdated dependencies, poor abstractions, missing tests)
- undocumented_component (components referenced but not described)
- cross_server_coupling (tight coupling between servers/services)
- data_loss_exposure (risk of data loss due to missing persistence, backups, or transactions)

Return ONLY a valid JSON object with this exact structure:
{
  "findings": [
    {
      "id": "RISK-001",
      "category": "<one of the 7 categories above>",
      "severity": "<critical|high|medium|low>",
      "title": "<short title>",
      "description": "<detailed description>",
      "affected_components": ["<component1>", "<component2>"],
      "recommendation": "<actionable recommendation>"
    }
  ],
  "summary": "<overall summary of the risk landscape>"
}

Number findings sequentially: RISK-001, RISK-002, etc.
Do not include any text outside the JSON object.
"""


class RiskAnalysisTool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def analyze(self, context: DocumentContext) -> RiskReport:
        if not context.raw_text.strip():
            return RiskReport(
                findings=[],
                summary="No content available for analysis.",
                generated_at=_now(),
            )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Analyze the following architecture documentation:\n\n{context.raw_text}",
            },
        ]

        try:
            response = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMUnavailableError(f"LLM returned invalid JSON: {exc}") from exc

        findings: list[RiskFinding] = []
        for item in data.get("findings", []):
            findings.append(
                RiskFinding(
                    id=item["id"],
                    category=RiskCategory(item["category"]),
                    severity=item["severity"],
                    title=item["title"],
                    description=item["description"],
                    affected_components=item.get("affected_components", []),
                    recommendation=item["recommendation"],
                )
            )

        summary = data.get("summary", "").strip() or "Risk analysis complete."

        return RiskReport(findings=findings, summary=summary, generated_at=_now())
