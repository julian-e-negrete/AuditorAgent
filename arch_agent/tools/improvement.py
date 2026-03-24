"""ImprovementTool — generates concrete improvement proposals from a DocumentContext."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import litellm

from arch_agent.config import Settings
from arch_agent.exceptions import LLMUnavailableError
from arch_agent.models.documents import DocumentContext


@dataclass
class Improvement:
    title: str
    rationale: str
    decision_context: str
    suggested_action: str
    priority: Literal["high", "medium", "low"]


_SYSTEM_PROMPT = """\
You are a senior system architect generating concrete improvement proposals.
Analyze the provided architecture documentation and suggest actionable improvements.

Return ONLY a valid JSON array with this exact structure:
[
  {
    "title": "<short improvement title>",
    "rationale": "<why this improvement is needed>",
    "decision_context": "<context for the decision>",
    "suggested_action": "<concrete action to take>",
    "priority": "<high|medium|low>"
  }
]

Do not include any text outside the JSON array.
"""


class ImprovementTool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def suggest(
        self, context: DocumentContext, focus: str | None = None
    ) -> list[Improvement]:
        content = context.raw_text
        user_content = "Suggest improvements for the following architecture documentation"
        if focus:
            user_content += f" (focus on: {focus})"
        user_content += f":\n\n{content}"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
            )
            raw = response.choices[0].message.content or "[]"
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMUnavailableError(f"LLM returned invalid JSON: {exc}") from exc

        improvements: list[Improvement] = []
        for item in data:
            improvements.append(
                Improvement(
                    title=item["title"],
                    rationale=item["rationale"],
                    decision_context=item["decision_context"],
                    suggested_action=item["suggested_action"],
                    priority=item["priority"],
                )
            )

        return improvements
