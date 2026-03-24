"""Unit tests for RiskAnalysisTool and DocGenerationTool (Tasks 7.1, 9.1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arch_agent.config import Settings
from arch_agent.models.docs import DesignDecision
from arch_agent.models.documents import DocumentContext
from arch_agent.tools.docgen import DocGenerationTool
from arch_agent.tools.risk import RiskAnalysisTool


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    return Settings(
        LLM_PROVIDER="openai",
        LLM_API_KEY="test-key",
        LLM_MODEL="gpt-4o",
        GLPI_PROXY_URL="http://localhost:8080",
        GLPI_CLIENT_ID="cid",
        GLPI_CLIENT_SECRET="csecret",
        GLPI_USERNAME="user",
        GLPI_PASSWORD="pass",
    )


def _empty_context() -> DocumentContext:
    return DocumentContext(sections=[], raw_text="", source_files=[])


def _context_with_text(text: str) -> DocumentContext:
    return DocumentContext(sections=[], raw_text=text, source_files=["test.md"])


def _mock_llm_response(content: str):
    """Build a mock litellm response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _risk_llm_payload(findings: list[dict], summary: str = "Test summary") -> str:
    return json.dumps({"findings": findings, "summary": summary})


# ---------------------------------------------------------------------------
# RiskAnalysisTool — empty context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_empty_context_returns_zero_findings(settings):
    tool = RiskAnalysisTool(settings)
    report = await tool.analyze(_empty_context())
    assert report.findings == []
    assert report.summary == "No content available for analysis."


@pytest.mark.asyncio
async def test_risk_whitespace_only_context_returns_zero_findings(settings):
    tool = RiskAnalysisTool(settings)
    ctx = DocumentContext(sections=[], raw_text="   \n\t  ", source_files=[])
    report = await tool.analyze(ctx)
    assert report.findings == []


# ---------------------------------------------------------------------------
# RiskAnalysisTool — LLM response parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_parses_llm_json_into_risk_report(settings):
    findings_data = [
        {
            "id": "RISK-001",
            "category": "SPOF",
            "severity": "high",
            "title": "Single DB instance",
            "description": "No replica configured.",
            "affected_components": ["postgres"],
            "recommendation": "Add read replica.",
        },
        {
            "id": "RISK-002",
            "category": "security_gap",
            "severity": "critical",
            "title": "No auth on API",
            "description": "API endpoint has no authentication.",
            "affected_components": ["api-server"],
            "recommendation": "Add JWT auth.",
        },
    ]
    payload = _risk_llm_payload(findings_data, summary="Two risks found.")

    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response(payload))):
        tool = RiskAnalysisTool(settings)
        report = await tool.analyze(_context_with_text("some architecture text"))

    assert len(report.findings) == 2
    assert report.summary == "Two risks found."
    assert report.findings[0].id == "RISK-001"
    assert report.findings[1].id == "RISK-002"


@pytest.mark.asyncio
async def test_risk_finding_ids_are_unique(settings):
    findings_data = [
        {
            "id": f"RISK-{i:03d}",
            "category": "tech_debt",
            "severity": "low",
            "title": f"Issue {i}",
            "description": "desc",
            "affected_components": [],
            "recommendation": "fix it",
        }
        for i in range(1, 6)
    ]
    payload = _risk_llm_payload(findings_data, summary="Five issues.")

    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response(payload))):
        tool = RiskAnalysisTool(settings)
        report = await tool.analyze(_context_with_text("arch docs"))

    ids = [f.id for f in report.findings]
    assert len(ids) == len(set(ids)), "Finding IDs must be unique"


@pytest.mark.asyncio
async def test_risk_report_has_non_empty_summary(settings):
    payload = _risk_llm_payload([], summary="No risks found.")

    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response(payload))):
        tool = RiskAnalysisTool(settings)
        report = await tool.analyze(_context_with_text("clean architecture"))

    assert report.summary.strip() != ""


# ---------------------------------------------------------------------------
# DocGenerationTool — generate_adr
# ---------------------------------------------------------------------------


def _sample_decision(title: str = "Use Redis for caching") -> DesignDecision:
    return DesignDecision(
        title=title,
        context="Need caching layer",
        decision="Use Redis",
        rationale="Low latency, widely supported",
        consequences="Adds operational complexity",
        alternatives_considered=["Memcached", "In-process cache"],
        status="proposed",
    )


@pytest.mark.asyncio
async def test_generate_adr_returns_adr_document(settings):
    adr_content = "# ADR-001: Use Redis for caching\n\n## Status\nProposed\n"

    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response(adr_content))):
        tool = DocGenerationTool(settings)
        adr = await tool.generate_adr(_sample_decision())

    assert adr.content == adr_content
    assert adr.adr_number == 1


@pytest.mark.asyncio
async def test_generate_adr_filename_pattern(settings):
    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response("# ADR"))):
        tool = DocGenerationTool(settings)
        adr = await tool.generate_adr(_sample_decision("Use Redis for caching"))

    import re
    assert re.match(r"adr-\d{3}-[a-z0-9-]+\.md", adr.filename), f"Bad filename: {adr.filename}"
    assert adr.filename == "adr-001-use-redis-for-caching.md"


@pytest.mark.asyncio
async def test_generate_adr_does_not_write_to_disk(settings, tmp_path):
    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response("# ADR"))):
        tool = DocGenerationTool(settings)
        adr = await tool.generate_adr(_sample_decision())

    # No file should have been created
    assert not list(tmp_path.iterdir())
    # Also check current dir has no new adr files
    import os
    cwd_adrs = list(Path(os.getcwd()).glob("adr-*.md"))
    assert cwd_adrs == [], f"Unexpected ADR files on disk: {cwd_adrs}"


@pytest.mark.asyncio
async def test_generate_adr_sequential_numbering(settings):
    with patch("litellm.acompletion", new=AsyncMock(return_value=_mock_llm_response("# ADR"))):
        tool = DocGenerationTool(settings)
        adr1 = await tool.generate_adr(_sample_decision("Decision One"))
        adr2 = await tool.generate_adr(_sample_decision("Decision Two"))
        adr3 = await tool.generate_adr(_sample_decision("Decision Three"))

    assert adr1.adr_number == 1
    assert adr2.adr_number == 2
    assert adr3.adr_number == 3
    assert adr1.filename.startswith("adr-001-")
    assert adr2.filename.startswith("adr-002-")
    assert adr3.filename.startswith("adr-003-")


# ---------------------------------------------------------------------------
# DocGenerationTool — write
# ---------------------------------------------------------------------------


def test_write_writes_content_to_path(settings, tmp_path):
    from arch_agent.models.docs import BaseDocument

    tool = DocGenerationTool(settings)
    doc = BaseDocument(content="# Hello\n\nThis is content.")
    output = tmp_path / "output.md"

    tool.write(doc, output)

    assert output.exists()
    assert output.read_text(encoding="utf-8") == "# Hello\n\nThis is content."


def test_write_creates_parent_directories(settings, tmp_path):
    from arch_agent.models.docs import BaseDocument

    tool = DocGenerationTool(settings)
    doc = BaseDocument(content="content")
    output = tmp_path / "deep" / "nested" / "doc.md"

    tool.write(doc, output)

    assert output.exists()
    assert output.read_text(encoding="utf-8") == "content"
