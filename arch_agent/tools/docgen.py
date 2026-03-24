"""DocGenerationTool — produces formal documentation artifacts (ADRs, diagrams, runbooks)."""

from __future__ import annotations

import re
from pathlib import Path

import litellm

from arch_agent.config import Settings
from arch_agent.exceptions import LLMUnavailableError
from arch_agent.models.docs import ADRDocument, BaseDocument, DesignDecision, RunbookDocument
from arch_agent.models.documents import DocumentContext


def _slugify(title: str) -> str:
    """Convert a title to a URL-friendly slug."""
    slug = title.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


class DocGenerationTool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._adr_counter = 0

    async def generate_adr(self, decision: DesignDecision) -> ADRDocument:
        self._adr_counter += 1
        adr_number = self._adr_counter
        slug = _slugify(decision.title)
        filename = f"adr-{adr_number:03d}-{slug}.md"

        prompt = f"""\
Generate a complete Architecture Decision Record (ADR) in Markdown format for the following decision.

Title: {decision.title}
Status: {decision.status}
Context: {decision.context}
Decision: {decision.decision}
Rationale: {decision.rationale}
Consequences: {decision.consequences}
Alternatives Considered: {', '.join(decision.alternatives_considered) if decision.alternatives_considered else 'None'}

Use standard ADR format with sections: Title, Status, Context, Decision, Rationale, Consequences, Alternatives Considered.
Return only the Markdown content, no extra commentary.
"""

        messages = [
            {"role": "system", "content": "You are a technical writer producing Architecture Decision Records."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        return ADRDocument(
            content=content,
            decision=decision,
            adr_number=adr_number,
            filename=filename,
        )

    async def generate_diagram(self, context: DocumentContext, diagram_type: str) -> str:
        prompt = f"""\
Generate a Mermaid diagram of type "{diagram_type}" based on the following architecture documentation.

{context.raw_text}

Return only the Mermaid diagram block (```mermaid ... ```), no extra commentary.
"""

        messages = [
            {"role": "system", "content": "You are a technical architect generating Mermaid diagrams."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def generate_runbook(self, context: DocumentContext, scenario: str) -> RunbookDocument:
        prompt = f"""\
Generate a step-by-step runbook for the following scenario based on the architecture documentation.

Scenario: {scenario}

Architecture context:
{context.raw_text}

Return a runbook with:
1. A brief overview
2. Numbered steps for remediation
3. Verification steps

Format as plain Markdown.
"""

        messages = [
            {"role": "system", "content": "You are a senior SRE writing operational runbooks."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        # Extract numbered steps from the content
        steps = re.findall(r"^\d+\.\s+(.+)$", content, re.MULTILINE)

        return RunbookDocument(content=content, scenario=scenario, steps=steps)

    def write(self, doc: BaseDocument, output_path: Path) -> None:
        """Write doc.content to output_path. Only writes when explicitly called."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(doc.content, encoding="utf-8")
