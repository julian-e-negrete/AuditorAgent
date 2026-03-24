# Implementation Plan: architecture-doc-agent

## Overview

Incremental implementation of the LLM-backed architecture agent in Python. Each task builds on the previous, ending with a fully wired CLI and optional FastAPI interface.

## Tasks

- [x] 1. Project scaffold and core data models
  - Create package structure: `arch_agent/`, `arch_agent/tools/`, `arch_agent/models/`, `tests/`
  - Implement `DocumentSection`, `DocumentContext` dataclasses in `arch_agent/models/documents.py`
  - Implement `RiskFinding`, `RiskReport`, `RiskCategory` in `arch_agent/models/risk.py`
  - Implement `DesignDecision`, `ADRDocument`, `RunbookDocument`, `BaseDocument` in `arch_agent/models/docs.py`
  - Implement `Ticket` dataclass in `arch_agent/models/glpi.py`
  - Implement `Message` dataclass and `Literal["user", "assistant"]` role type in `arch_agent/models/memory.py`
  - Implement custom exceptions: `IngestionError`, `GLPIUnavailableError`, `LLMUnavailableError` in `arch_agent/exceptions.py`
  - Add `pyproject.toml` with all dependencies (typer, fastapi, uvicorn, langchain, litellm, httpx, pydantic, pydantic-settings, python-dotenv, hypothesis, pytest, pytest-asyncio)
  - _Requirements: 1.1, 1.6, 2.1, 6.1, 7.1, 9.3_

- [x] 2. Configuration and settings
  - Implement `Settings` class in `arch_agent/config.py` using `pydantic-settings`, loading `LLM_PROVIDER`, `LLM_API_KEY`, `GLPI_CLIENT_ID`, `GLPI_CLIENT_SECRET` from environment
  - Ensure no credentials are hardcoded; all sourced from `.env`
  - _Requirements: 10.1_

- [x] 3. Implement `ArchiveIngestionTool`
  - [x] 3.1 Implement `ArchiveIngestionTool.load()` in `arch_agent/tools/ingestion.py`
    - Read each path as UTF-8; raise `IngestionError(path, reason)` before any LLM call if path missing or unreadable
    - Parse Markdown into typed `DocumentSection` objects (prose, mermaid, code, table)
    - Deduplicate overlapping sections across files
    - Populate `DocumentContext.source_files` with basenames only
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 3.2 Implement `ArchiveIngestionTool.load_directory()` using `glob("**/*.md")`
    - _Requirements: 1.2_

  - [ ]* 3.3 Write property test for source file round-trip (Property 1)
    - **Property 1: Document ingestion source file round-trip**
    - **Validates: Requirements 1.5**

  - [ ]* 3.4 Write property test for section type coverage (Property 2)
    - **Property 2: Section type coverage**
    - **Validates: Requirements 1.3**

  - [ ]* 3.5 Write property test for deduplication invariant (Property 3)
    - **Property 3: Deduplication invariant**
    - **Validates: Requirements 1.4**

  - [ ]* 3.6 Write property test for ingestion error leaves no partial state (Property 4)
    - **Property 4: Ingestion error leaves no partial state**
    - **Validates: Requirements 1.6, 1.7, 9.5**

- [x] 4. Implement `ConversationMemory`
  - [x] 4.1 Implement `ConversationMemory` in `arch_agent/memory.py`
    - `add_message`, `get_history(max_tokens)`, `add_context`, `get_context`, `clear`
    - Token budget: return most recent messages fitting within `max_tokens`
    - Session-scoped; no shared state between instances
    - _Requirements: 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 4.2 Write property test for conversation history insertion order (Property 10)
    - **Property 10: Conversation history insertion order**
    - **Validates: Requirements 4.5, 5.1, 5.4**

  - [ ]* 4.3 Write property test for token budget enforcement (Property 11)
    - **Property 11: Token budget enforcement**
    - **Validates: Requirements 4.6, 5.2**

  - [ ]* 4.4 Write property test for context key-value round-trip (Property 12)
    - **Property 12: Context key-value round-trip**
    - **Validates: Requirements 5.3**

  - [ ]* 4.5 Write property test for session isolation (Property 13)
    - **Property 13: Session isolation**
    - **Validates: Requirements 5.5**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `GLPITool`
  - [x] 6.1 Implement `GLPITool` in `arch_agent/tools/glpi.py` using `httpx.AsyncClient`
    - `create_server_ticket(title, description, agent="kiro", urgency=3) -> int`
    - `complete_server_ticket(ticket_id, solution) -> None`
    - `list_server_tickets() -> list[Ticket]`
    - Raise `GLPIUnavailableError` on network failure; no silent partial state
    - Transparent OAuth re-authentication on token expiry (POST `/api/v2.2/token`, one retry)
    - Store OAuth token in memory only; never write to disk
    - Mask `Authorization` and `client_secret` in log output
    - Use 30s timeout on all requests
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.1, 9.2, 10.2, 10.3_

  - [ ]* 6.2 Write property test for GLPI ticket creation round-trip (Property 18)
    - **Property 18: GLPI ticket creation round-trip**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 6.3 Write property test for GLPI ticket completion (Property 19)
    - **Property 19: GLPI ticket completion**
    - **Validates: Requirements 7.3**

  - [ ]* 6.4 Write property test for GLPIUnavailableError on unreachable proxy (Property 20)
    - **Property 20: GLPIUnavailableError on unreachable proxy**
    - **Validates: Requirements 7.5, 9.1**

  - [ ]* 6.5 Write property test for OAuth token not written to disk (Property 21)
    - **Property 21: OAuth token not written to disk**
    - **Validates: Requirements 10.2**

  - [ ]* 6.6 Write property test for sensitive headers masked in logs (Property 22)
    - **Property 22: Sensitive headers masked in logs**
    - **Validates: Requirements 10.3**

- [x] 7. Implement `RiskAnalysisTool`
  - [x] 7.1 Implement `RiskAnalysisTool.analyze()` in `arch_agent/tools/risk.py`
    - Build LLM prompt from `DocumentContext.raw_text` covering all 7 risk categories
    - Parse LLM response into `RiskReport` with unique finding IDs (`RISK-NNN`), valid severities, non-empty summary
    - Return zero-finding report with explanatory summary when `raw_text` is empty
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 7.2 Write property test for RiskReport structural invariants (Property 5)
    - **Property 5: RiskReport structural invariants**
    - **Validates: Requirements 2.3, 2.4, 2.5**

- [x] 8. Implement `ImprovementTool`
  - Implement `ImprovementTool.suggest()` in `arch_agent/tools/improvement.py`
  - Build LLM prompt from `DocumentContext`; optionally filter by `focus` string
  - Return `list[Improvement]` with rationale and ADR-style framing
  - _Requirements: 4.1, 4.3_

- [x] 9. Implement `DocGenerationTool`
  - [x] 9.1 Implement `DocGenerationTool` in `arch_agent/tools/docgen.py`
    - `generate_adr(decision) -> ADRDocument`: sequential `adr_number`, filename `adr-{NNN}-{slug}.md`, valid Markdown, no disk write
    - `generate_diagram(context, diagram_type) -> str`: return valid Mermaid block
    - `generate_runbook(context, scenario) -> RunbookDocument`: step-by-step remediation
    - `write(doc, output_path)`: write `doc.content` to path only when explicitly called
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 10.5_

  - [ ]* 9.2 Write property test for ADR filename and content format (Property 14)
    - **Property 14: ADR filename and content format**
    - **Validates: Requirements 6.1, 6.3**

  - [ ]* 9.3 Write property test for ADR sequential numbering (Property 15)
    - **Property 15: ADR sequential numbering**
    - **Validates: Requirements 6.2**

  - [ ]* 9.4 Write property test for generate_adr does not write to disk (Property 16)
    - **Property 16: generate_adr does not write to disk**
    - **Validates: Requirements 6.4, 10.5**

  - [ ]* 9.5 Write property test for write round-trip (Property 17)
    - **Property 17: write round-trip**
    - **Validates: Requirements 6.5**

- [x] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement `Orchestrator`
  - [x] 11.1 Implement `Orchestrator` in `arch_agent/orchestrator.py`
    - `run_review(request) -> AsyncIterator[str]`: ingest → LLM stream → parse findings → auto-ticket if enabled
    - Map `critical` → urgency 1, `high` → urgency 2 when calling `GLPITool.create_server_ticket`
    - Store `DocumentContext` in session after review
    - Do not mutate source files
    - Raise `LLMUnavailableError` on LLM failure; preserve session memory
    - Operate in degraded mode when GLPI is unreachable (notify user, continue review/chat)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 9.1, 9.2, 9.3, 9.4_

  - [x] 11.2 Implement `Orchestrator.run_chat()`: load memory → build prompt with history → intent classification → tool dispatch or LLM stream → update memory
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 11.3 Implement `Orchestrator.run_generate()`: dispatch to `DocGenerationTool` based on `GenerateRequest.doc_type`
    - _Requirements: 4.3_

  - [ ]* 11.4 Write property test for review stream liveness (Property 6)
    - **Property 6: Review stream liveness**
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 11.5 Write property test for auto-ticket count matches high/critical findings (Property 7)
    - **Property 7: Auto-ticket count matches high/critical findings**
    - **Validates: Requirements 3.3**

  - [ ]* 11.6 Write property test for severity-to-urgency mapping (Property 8)
    - **Property 8: Severity-to-urgency mapping**
    - **Validates: Requirements 3.4**

  - [ ]* 11.7 Write property test for review does not mutate source files (Property 9)
    - **Property 9: Review does not mutate source files**
    - **Validates: Requirements 3.5**

- [x] 12. Implement CLI with Typer
  - Implement `arch_agent/cli.py` using Typer
  - `review` command: accepts one or more file paths + `--auto-ticket` flag; calls `Orchestrator.run_review()` and streams output
  - `review --dir PATH`: recursively loads all `**/*.md` files; calls `Orchestrator.run_review()`
  - `chat` command: interactive REPL with optional `--context` flag to pre-load files
  - `generate adr --title TEXT`, `generate diagram --type TYPE --output PATH`, `generate runbook --scenario TEXT` subcommands
  - Exit code 0 on success, non-zero with descriptive message on `IngestionError`, `LLMUnavailableError`, `GLPIUnavailableError`
  - Register `arch-agent` entry point in `pyproject.toml`
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 13. Implement optional FastAPI interface
  - Implement `arch_agent/api.py` with FastAPI app on port 8000
  - `POST /review` → `Orchestrator.run_review()` with streaming response
  - `POST /chat` → `Orchestrator.run_chat()` with streaming response
  - `POST /generate` → `Orchestrator.run_generate()`
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 14. Wire everything together and final integration
  - [x] 14.1 Implement `Orchestrator.from_env()` class method loading `Settings` and constructing all tools
    - _Requirements: 10.1, 10.4_

  - [x] 14.2 Ensure `arch_agent/__init__.py` exports `Orchestrator`, `ReviewRequest`, and key models for Python API usage
    - _Requirements: 3.1, 4.1_

  - [ ]* 14.3 Write integration tests for end-to-end review flow against real local Markdown files (mocked LLM, no GLPI)
    - _Requirements: 3.1, 3.2, 3.5, 3.6_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis`; unit/integration tests use `pytest` + `pytest-asyncio`
- GLPI integration tests require a live `.env` with proxy credentials and are excluded from CI by default
- The FastAPI interface (task 13) is optional and can be deferred after the CLI is working
