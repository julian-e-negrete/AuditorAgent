"""Orchestrator — central coordinator for the architecture doc agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Literal

import litellm

from arch_agent.config import Settings
from arch_agent.exceptions import GLPIUnavailableError, LLMUnavailableError
from arch_agent.memory import ConversationMemory
from arch_agent.models.docs import ADRDocument, ArchDocument, BaseDocument, DesignDecision, RunbookDocument
from arch_agent.models.documents import DocumentContext
from arch_agent.models.risk import RiskFinding, RiskReport
from arch_agent.tools.docgen import DocGenerationTool
from arch_agent.tools.glpi import GLPITool
from arch_agent.tools.improvement import ImprovementTool
from arch_agent.tools.ingestion import ArchiveIngestionTool
from arch_agent.tools.risk import RiskAnalysisTool

logger = logging.getLogger(__name__)

ARCHITECT_PERSONA = (
    "You are a senior system architect with deep expertise in distributed systems, "
    "infrastructure, and software design. You analyze architecture documentation, "
    "identify risks and improvements, and engage in technical design conversations. "
    "Be precise, actionable, and reference specific components from the provided documentation."
)

_SEVERITY_TO_URGENCY: dict[str, int] = {
    "critical": 1,
    "high": 2,
}


# ---------------------------------------------------------------------------
# Request / Response dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ReviewRequest:
    files: list[Path]
    auto_ticket: bool = False


@dataclass
class GenerateRequest:
    doc_type: Literal["adr", "diagram", "runbook"]
    title: str | None = None         # for adr
    diagram_type: str | None = None  # for diagram
    scenario: str | None = None      # for runbook
    output_path: Path | None = None


@dataclass
class GeneratedDoc:
    content: str
    filename: str | None = None
    doc_type: str = ""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        ingestion_tool: ArchiveIngestionTool,
        risk_tool: RiskAnalysisTool,
        improvement_tool: ImprovementTool,
        docgen_tool: DocGenerationTool,
        glpi_tool: GLPITool,
    ) -> None:
        self._settings = settings
        self._ingestion = ingestion_tool
        self._risk = risk_tool
        self._improvement = improvement_tool
        self._docgen = docgen_tool
        self._glpi = glpi_tool
        self._sessions: dict[str, dict] = {}
        self._memories: dict[str, ConversationMemory] = {}

    @classmethod
    def from_env(cls) -> "Orchestrator":
        settings = Settings()  # type: ignore[call-arg]
        return cls(
            settings=settings,
            ingestion_tool=ArchiveIngestionTool(),
            risk_tool=RiskAnalysisTool(settings),
            improvement_tool=ImprovementTool(settings),
            docgen_tool=DocGenerationTool(settings),
            glpi_tool=GLPITool(settings),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_memory(self, session_id: str) -> ConversationMemory:
        if session_id not in self._memories:
            self._memories[session_id] = ConversationMemory()
        return self._memories[session_id]

    def _get_session(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {}
        return self._sessions[session_id]

    # ------------------------------------------------------------------
    # Task 11.1 — run_review
    # ------------------------------------------------------------------

    async def run_review(self, request: ReviewRequest) -> AsyncIterator[str]:
        # Phase 1: ingest — raises IngestionError if any file missing
        doc_context = self._ingestion.load(request.files)

        # Store in a default session keyed by a stable id
        session_id = "review"
        self._sessions[session_id] = {"doc_context": doc_context}

        # Phase 2: build LLM prompt
        system_msg = {"role": "system", "content": ARCHITECT_PERSONA}
        user_msg = {
            "role": "user",
            "content": (
                "Please perform a thorough architectural review of the following documentation. "
                "Identify risks, gaps, and improvement opportunities.\n\n"
                f"{doc_context.raw_text}"
            ),
        }
        messages = [system_msg, user_msg]

        # Phase 3: stream LLM response
        full_response = ""
        try:
            stream = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    yield delta
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        # Phase 4: parse RiskReport from full response (best-effort)
        report = await self._risk.analyze(doc_context)

        # Phase 5: auto-ticket for critical/high findings
        if request.auto_ticket:
            for finding in report.findings:
                if finding.severity in _SEVERITY_TO_URGENCY:
                    urgency = _SEVERITY_TO_URGENCY[finding.severity]
                    try:
                        ticket_id = await self._glpi.create_server_ticket(
                            title=finding.title,
                            description=f"{finding.description}\n\nRecommendation: {finding.recommendation}",
                            agent="kiro",
                            urgency=urgency,
                        )
                        finding.glpi_ticket_id = ticket_id
                        logger.info("Created GLPI ticket #%d for finding %s", ticket_id, finding.id)
                    except GLPIUnavailableError as exc:
                        logger.warning("GLPI unavailable, skipping ticket for %s: %s", finding.id, exc)

    # ------------------------------------------------------------------
    # Task 11.2 — run_chat
    # ------------------------------------------------------------------

    async def run_chat(self, message: str, session_id: str) -> AsyncIterator[str]:
        memory = self._get_memory(session_id)
        session = self._get_session(session_id)
        doc_context = session.get("doc_context")

        # Build system prompt with optional doc context
        system_content = ARCHITECT_PERSONA
        if doc_context is not None:
            system_content += (
                "\n\nYou have access to the following architecture documentation:\n\n"
                + doc_context.raw_text
            )

        # Build messages: system + history + new user message
        history = memory.get_history()
        messages = (
            [{"role": "system", "content": system_content}]
            + [{"role": msg.role, "content": msg.content} for msg in history]
            + [{"role": "user", "content": message}]
        )

        # Classify intent
        msg_lower = message.lower()
        if "generate adr" in msg_lower or "create adr" in msg_lower:
            intent = "generate_adr"
        elif "generate diagram" in msg_lower:
            intent = "generate_diagram"
        elif "generate runbook" in msg_lower:
            intent = "generate_runbook"
        elif "create ticket" in msg_lower or "open ticket" in msg_lower:
            intent = "create_ticket"
        else:
            intent = "chat"

        if intent == "generate_adr":
            decision = DesignDecision(
                title=message,
                context="Generated from conversation",
                decision="To be determined",
                rationale="Based on architectural discussion",
                consequences="TBD",
                alternatives_considered=[],
                status="proposed",
            )
            adr = await self._docgen.generate_adr(decision)
            memory.add_message("user", message)
            memory.add_message("assistant", adr.content)
            yield adr.content
            return

        if intent == "generate_diagram":
            if doc_context is not None:
                diagram_content = await self._docgen.generate_diagram(doc_context, "system")
            else:
                diagram_content = "No document context loaded. Please run a review first."
            memory.add_message("user", message)
            memory.add_message("assistant", diagram_content)
            yield diagram_content
            return

        if intent == "generate_runbook":
            if doc_context is not None:
                runbook = await self._docgen.generate_runbook(doc_context, message)
                content = runbook.content
            else:
                content = "No document context loaded. Please run a review first."
            memory.add_message("user", message)
            memory.add_message("assistant", content)
            yield content
            return

        if intent == "create_ticket":
            try:
                ticket_id = await self._glpi.create_server_ticket(
                    title=message,
                    description=message,
                    agent="kiro",
                    urgency=3,
                )
                response = f"Created GLPI ticket #{ticket_id}"
            except GLPIUnavailableError:
                response = "GLPI unavailable: ticket creation skipped"
            memory.add_message("user", message)
            memory.add_message("assistant", response)
            yield response
            return

        # Default: stream LLM response
        full_response = ""
        try:
            stream = await litellm.acompletion(
                model=self._settings.LLM_MODEL,
                messages=messages,
                api_key=self._settings.LLM_API_KEY,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    yield delta
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

        memory.add_message("user", message)
        memory.add_message("assistant", full_response)

    # ------------------------------------------------------------------
    # Task 11.3 — run_generate
    # ------------------------------------------------------------------

    async def run_generate(self, request: GenerateRequest) -> GeneratedDoc:
        doc: BaseDocument

        if request.doc_type == "adr":
            title = request.title or "Untitled Decision"
            decision = DesignDecision(
                title=title,
                context="Generated via run_generate",
                decision="To be determined",
                rationale="Based on architectural discussion",
                consequences="TBD",
                alternatives_considered=[],
                status="proposed",
            )
            adr: ADRDocument = await self._docgen.generate_adr(decision)
            doc = adr
            result = GeneratedDoc(
                content=adr.content,
                filename=adr.filename,
                doc_type="adr",
            )

        elif request.doc_type == "diagram":
            diagram_type = request.diagram_type or "system"
            # Try to get context from any active session
            doc_context = None
            for session in self._sessions.values():
                if "doc_context" in session:
                    doc_context = session["doc_context"]
                    break
            if doc_context is None:
                doc_context = DocumentContext(sections=[], raw_text="", source_files=[])
            content = await self._docgen.generate_diagram(doc_context, diagram_type)
            doc = ArchDocument(content=content)
            result = GeneratedDoc(content=content, filename=None, doc_type="diagram")

        elif request.doc_type == "runbook":
            scenario = request.scenario or "General operational scenario"
            doc_context = None
            for session in self._sessions.values():
                if "doc_context" in session:
                    doc_context = session["doc_context"]
                    break
            if doc_context is None:
                doc_context = DocumentContext(sections=[], raw_text="", source_files=[])
            runbook: RunbookDocument = await self._docgen.generate_runbook(doc_context, scenario)
            doc = runbook
            result = GeneratedDoc(content=runbook.content, filename=None, doc_type="runbook")

        else:
            raise ValueError(f"Unknown doc_type: {request.doc_type!r}")

        # Write to disk if output_path specified
        if request.output_path is not None and hasattr(doc, "content"):
            self._docgen.write(doc, request.output_path)  # type: ignore[arg-type]

        return result
