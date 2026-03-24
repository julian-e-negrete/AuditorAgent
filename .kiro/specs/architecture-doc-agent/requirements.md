# Requirements Document

## Introduction

The `architecture-doc-agent` is an LLM-backed conversational AI agent that acts as a senior system architect. It ingests local architecture documents (Markdown, Mermaid diagrams, spec files) as its knowledge base, reasons about the system to identify risks and improvements, and engages in natural-language design conversations that culminate in formal documentation output (Mermaid diagrams, ADRs, runbooks). It integrates with the existing GLPI Proxy at `100.112.16.115:8080` to create and close tickets for identified issues and completed design tasks.

The agent operates entirely from documents and conversation — it does not SSH into servers, scrape live infrastructure, or poll APIs automatically.

---

## Glossary

- **Agent**: The `architecture-doc-agent` system as a whole.
- **Orchestrator**: The central coordinator component that manages the LLM conversation loop, routes user intent to tools, and streams responses.
- **ArchiveIngestionTool**: The component responsible for loading and parsing local Markdown, Mermaid, and spec files into a `DocumentContext`.
- **RiskAnalysisTool**: The component that uses the LLM to identify architectural risks from a `DocumentContext`.
- **ImprovementTool**: The component that generates concrete improvement proposals from a `DocumentContext`.
- **DocGenerationTool**: The component that produces formal documentation artifacts (ADRs, diagrams, runbooks).
- **GLPITool**: The component that creates and closes GLPI tickets via the proxy at `100.112.16.115:8080`.
- **ConversationMemory**: The session-scoped in-memory store for conversation history and accumulated design context.
- **DocumentContext**: The structured representation of ingested documents, including sections, raw text, and source file metadata.
- **RiskReport**: The output of a risk analysis, containing a list of `RiskFinding` objects and a summary.
- **RiskFinding**: A single identified architectural risk with severity, category, description, and recommendation.
- **ADRDocument**: An Architecture Decision Record document produced by the `DocGenerationTool`.
- **GLPI_Proxy**: The HTTP proxy service at `100.112.16.115:8080` that mediates access to the GLPI ticketing system.
- **Session**: A single interactive run of the agent, scoped to one `ConversationMemory` instance.
- **CLI**: The command-line interface built with Typer.
- **API**: The optional FastAPI HTTP interface exposed on port 8000.

---

## Requirements

### Requirement 1: Document Ingestion

**User Story:** As an architect, I want to load local architecture documents into the agent, so that it can reason about my system from existing documentation.

#### Acceptance Criteria

1. WHEN a user provides one or more file paths, THE ArchiveIngestionTool SHALL load and parse each file into a `DocumentContext`.
2. WHEN a user provides a directory path, THE ArchiveIngestionTool SHALL recursively discover and load all Markdown files matching `**/*.md`.
3. WHEN parsing a document, THE ArchiveIngestionTool SHALL extract Mermaid diagrams, code blocks, tables, and prose as typed `DocumentSection` objects.
4. WHEN multiple files are loaded, THE ArchiveIngestionTool SHALL deduplicate overlapping content across files.
5. THE ArchiveIngestionTool SHALL populate `DocumentContext.source_files` with exactly the basenames of the input paths.
6. WHEN a provided path does not exist or is not readable as UTF-8, THE ArchiveIngestionTool SHALL raise an `IngestionError` before any LLM call is made.
7. IF an `IngestionError` is raised, THEN THE ArchiveIngestionTool SHALL not store any partial context in the session.

---

### Requirement 2: Architecture Risk Analysis

**User Story:** As an architect, I want the agent to analyze my architecture documents and identify risks, so that I can address vulnerabilities and gaps proactively.

#### Acceptance Criteria

1. WHEN a `DocumentContext` is provided, THE RiskAnalysisTool SHALL analyze it and return a `RiskReport`.
2. THE RiskAnalysisTool SHALL identify risks across the following categories: SPOF, security gaps, missing redundancy, tech debt, undocumented components, cross-server coupling, and data loss exposure.
3. THE RiskAnalysisTool SHALL assign each finding a severity of one of: `critical`, `high`, `medium`, or `low`.
4. THE RiskAnalysisTool SHALL assign each `RiskFinding` a unique `id` within the report.
5. THE RiskAnalysisTool SHALL produce a non-empty `summary` in every `RiskReport`.
6. WHEN the `DocumentContext.raw_text` is empty, THE RiskAnalysisTool SHALL return a `RiskReport` with zero findings and a summary indicating no content was available.

---

### Requirement 3: Architecture Review Flow

**User Story:** As an architect, I want to run a full architecture review from the CLI, so that I receive a streamed analysis of risks and improvements.

#### Acceptance Criteria

1. WHEN a review is requested with one or more valid file paths, THE Orchestrator SHALL ingest the documents, analyze them, and stream findings to the user.
2. THE Orchestrator SHALL yield at least one non-empty string chunk for any review request where files are non-empty and all paths exist.
3. WHEN `auto_ticket` is enabled and findings with severity `critical` or `high` exist, THE Orchestrator SHALL create a GLPI ticket for each such finding via the GLPITool.
4. WHEN creating tickets automatically, THE Orchestrator SHALL map `critical` severity to urgency 1 and `high` severity to urgency 2.
5. THE Orchestrator SHALL not mutate any source files during a review.
6. WHEN a review completes, THE Orchestrator SHALL store the resulting `DocumentContext` in the session for subsequent chat interactions.

---

### Requirement 4: Conversational Design Chat

**User Story:** As an architect, I want to have a natural-language conversation with the agent about my architecture, so that I can explore design decisions interactively.

#### Acceptance Criteria

1. WHEN a user sends a message, THE Orchestrator SHALL load the session's `ConversationMemory` and build an LLM prompt that includes conversation history and any loaded `DocumentContext`.
2. THE Orchestrator SHALL stream the LLM response back to the user in real time.
3. WHEN the user requests document generation within a chat, THE Orchestrator SHALL invoke the DocGenerationTool and stream the resulting document content.
4. WHEN the user requests ticket creation within a chat, THE Orchestrator SHALL invoke the GLPITool and confirm the created ticket ID to the user.
5. WHILE a chat session is active, THE ConversationMemory SHALL retain all messages in insertion order.
6. THE ConversationMemory SHALL enforce a token budget of 4096 tokens when returning history to prevent context window overflow.

---

### Requirement 5: Conversation Memory

**User Story:** As an architect, I want the agent to remember the context of our conversation, so that I don't have to repeat myself across turns.

#### Acceptance Criteria

1. THE ConversationMemory SHALL store messages with roles `user` or `assistant` in insertion order.
2. WHEN `get_history` is called with a `max_tokens` limit, THE ConversationMemory SHALL return the most recent messages that fit within that token budget.
3. THE ConversationMemory SHALL store arbitrary key-value design context via `add_context` and return it via `get_context`.
4. WHEN `clear` is called, THE ConversationMemory SHALL remove all messages and context.
5. THE ConversationMemory SHALL be scoped to a single session and SHALL NOT share state between sessions.

---

### Requirement 6: Document Generation

**User Story:** As an architect, I want the agent to produce formal documentation artifacts, so that design decisions are captured in a standard, reusable format.

#### Acceptance Criteria

1. WHEN a `DesignDecision` with non-empty required fields is provided, THE DocGenerationTool SHALL return an `ADRDocument` with a filename matching the pattern `adr-{NNN}-{slug}.md`.
2. THE DocGenerationTool SHALL assign `adr_number` sequentially across ADR generation calls within a session.
3. THE DocGenerationTool SHALL produce ADR content that is valid Markdown.
4. WHEN `generate_adr` is called, THE DocGenerationTool SHALL NOT write any file to disk.
5. WHEN `write` is explicitly called with a document and output path, THE DocGenerationTool SHALL write the document content to that path.
6. WHEN a Mermaid diagram is requested, THE DocGenerationTool SHALL return a string containing a valid Mermaid diagram block.
7. WHEN a runbook is requested for a given scenario, THE DocGenerationTool SHALL return a `RunbookDocument` with step-by-step remediation content.

---

### Requirement 7: GLPI Ticket Integration

**User Story:** As an architect, I want the agent to create and manage GLPI tickets for identified issues, so that findings are tracked in the existing ticketing system.

#### Acceptance Criteria

1. WHEN `create_server_ticket` is called with a non-empty title, non-empty description, and urgency in [1, 5], THE GLPITool SHALL create a ticket via the GLPI Proxy and return a positive integer ticket ID.
2. WHEN `create_server_ticket` succeeds, THE GLPITool SHALL return a ticket ID corresponding to a ticket with status `new` in GLPI.
3. WHEN `complete_server_ticket` is called with a valid ticket ID and solution, THE GLPITool SHALL mark the ticket as solved via the GLPI Proxy.
4. WHEN `list_server_tickets` is called, THE GLPITool SHALL return the current list of tickets from the GLPI Proxy.
5. IF the GLPI Proxy at `100.112.16.115:8080` is unreachable, THEN THE GLPITool SHALL raise a `GLPIUnavailableError` and SHALL NOT silently fail or write partial state.
6. WHEN a GLPI OAuth token has expired, THE GLPITool SHALL transparently re-authenticate via the proxy before retrying the failed request.
7. THE GLPITool SHALL use `agent="kiro"` and `urgency=3` as defaults when those parameters are not explicitly provided.

---

### Requirement 8: CLI Interface

**User Story:** As an architect, I want a command-line interface to interact with the agent, so that I can run reviews and generate documents from my terminal.

#### Acceptance Criteria

1. THE CLI SHALL expose a `review` command that accepts one or more file paths and an optional `--auto-ticket` flag.
2. THE CLI SHALL expose a `review` command variant that accepts a `--dir` option to review all Markdown files in a directory.
3. THE CLI SHALL expose a `chat` command that starts an interactive session, with an optional `--context` flag to pre-load files.
4. THE CLI SHALL expose a `generate` command with subcommands `adr`, `diagram`, and `runbook`.
5. WHEN a review completes successfully, THE CLI SHALL exit with code 0 and produce non-empty output.
6. WHEN an error occurs (file not found, LLM unavailable, GLPI unavailable), THE CLI SHALL display a descriptive error message and exit with a non-zero code.

---

### Requirement 9: Error Handling and Degraded Mode

**User Story:** As an architect, I want the agent to handle failures gracefully, so that a single unavailable service does not prevent me from using the rest of the agent's capabilities.

#### Acceptance Criteria

1. IF the GLPI Proxy is unreachable, THEN THE Agent SHALL continue operating in degraded mode, allowing review and chat to function normally.
2. IF the GLPI Proxy is unreachable, THEN THE Agent SHALL notify the user that ticket creation is unavailable.
3. IF the LLM provider is unavailable, THEN THE Orchestrator SHALL raise an `LLMUnavailableError` and surface a descriptive error message to the user.
4. WHEN an `LLMUnavailableError` occurs, THE ConversationMemory SHALL preserve the existing session history so context is not lost.
5. IF a file path passed to ingestion does not exist, THEN THE ArchiveIngestionTool SHALL raise an `IngestionError` with the path and reason before any LLM call.

---

### Requirement 10: Security and Credential Handling

**User Story:** As an operator, I want the agent to handle credentials securely, so that API keys and tokens are never exposed in logs or on disk.

#### Acceptance Criteria

1. THE Agent SHALL load all LLM API keys and GLPI credentials exclusively from environment variables via `pydantic-settings`.
2. THE GLPITool SHALL store OAuth tokens in memory only and SHALL NOT write them to disk.
3. THE Agent SHALL mask `Authorization` and `client_secret` headers in any logs it produces.
4. THE Agent SHALL NOT execute shell commands, SSH into servers, or make outbound network calls beyond the configured LLM provider and GLPI Proxy.
5. THE DocGenerationTool SHALL only write files to explicitly specified output paths provided by the caller.
