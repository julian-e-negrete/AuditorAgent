"""CLI entry-point for arch-agent using Typer."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from arch_agent.exceptions import GLPIUnavailableError, IngestionError, LLMUnavailableError
from arch_agent.orchestrator import GenerateRequest, Orchestrator, ReviewRequest

app = typer.Typer(name="arch-agent", help="LLM-backed architecture documentation agent.")
generate_app = typer.Typer(help="Generate architecture documents.")
app.add_typer(generate_app, name="generate")


# ---------------------------------------------------------------------------
# arch-agent review
# ---------------------------------------------------------------------------


@app.command()
def review(
    files: Optional[list[Path]] = typer.Argument(default=None, help="Markdown files to review."),
    dir: Optional[Path] = typer.Option(None, "--dir", help="Directory of .md files to review."),
    auto_ticket: bool = typer.Option(False, "--auto-ticket", help="Auto-create GLPI tickets for critical/high findings."),
) -> None:
    """Review architecture documentation files."""
    if dir is not None:
        target_files = list(dir.glob("*.md"))
    elif files:
        target_files = list(files)
    else:
        typer.echo("Error: provide FILES or --dir", err=True)
        raise typer.Exit(code=1)

    request = ReviewRequest(files=target_files, auto_ticket=auto_ticket)
    orchestrator = Orchestrator.from_env()

    async def _run() -> None:
        async for chunk in orchestrator.run_review(request):
            typer.echo(chunk, nl=False)
        typer.echo("")

    try:
        asyncio.run(_run())
    except IngestionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except LLMUnavailableError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except GLPIUnavailableError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# arch-agent chat
# ---------------------------------------------------------------------------


@app.command()
def chat(
    context: Optional[list[Path]] = typer.Option(None, "--context", help="Files to pre-load as context."),
) -> None:
    """Start an interactive chat session with the architecture agent."""
    orchestrator = Orchestrator.from_env()
    session_id = "cli-chat"

    async def _preload() -> None:
        if context:
            from arch_agent.orchestrator import ReviewRequest as RR
            req = RR(files=list(context), auto_ticket=False)
            # consume the stream to load context into session
            async for _ in orchestrator.run_review(req):
                pass

    try:
        asyncio.run(_preload())
    except (IngestionError, LLMUnavailableError, GLPIUnavailableError) as e:
        typer.echo(f"Error loading context: {e}", err=True)
        raise typer.Exit(code=1)

    async def _chat_turn(message: str) -> None:
        async for chunk in orchestrator.run_chat(message, session_id):
            typer.echo(chunk, nl=False)
        typer.echo("")

    typer.echo("arch-agent chat — type a message or press Ctrl+C / Enter empty line to exit.")
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip():
                break
            try:
                asyncio.run(_chat_turn(line))
            except (LLMUnavailableError, GLPIUnavailableError) as e:
                typer.echo(f"Error: {e}", err=True)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# arch-agent generate adr / diagram / runbook
# ---------------------------------------------------------------------------


@generate_app.command("adr")
def generate_adr(
    title: str = typer.Option(..., "--title", help="Title of the ADR."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write output to this file."),
) -> None:
    """Generate an Architecture Decision Record."""
    request = GenerateRequest(doc_type="adr", title=title, output_path=output)
    _run_generate(request)


@generate_app.command("diagram")
def generate_diagram(
    type: str = typer.Option("system", "--type", help="Diagram type (e.g. system, sequence)."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write output to this file."),
) -> None:
    """Generate an architecture diagram."""
    request = GenerateRequest(doc_type="diagram", diagram_type=type, output_path=output)
    _run_generate(request)


@generate_app.command("runbook")
def generate_runbook(
    scenario: str = typer.Option(..., "--scenario", help="Scenario description for the runbook."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write output to this file."),
) -> None:
    """Generate an operational runbook."""
    request = GenerateRequest(doc_type="runbook", scenario=scenario, output_path=output)
    _run_generate(request)


def _run_generate(request: GenerateRequest) -> None:
    orchestrator = Orchestrator.from_env()
    try:
        result = asyncio.run(orchestrator.run_generate(request))
        typer.echo(result.content)
        if request.output_path:
            typer.echo(f"Written to {request.output_path}")
    except (IngestionError, LLMUnavailableError, GLPIUnavailableError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
