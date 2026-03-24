"""Optional FastAPI interface for arch-agent."""

from __future__ import annotations

from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from arch_agent.orchestrator import GenerateRequest, Orchestrator, ReviewRequest

app = FastAPI(title="arch-agent API", version="0.1.0")

# Module-level singleton — lazily initialized on first request
_orchestrator: Optional[Orchestrator] = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator.from_env()
    return _orchestrator


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ReviewBody(BaseModel):
    files: list[str]
    auto_ticket: bool = False


class ChatBody(BaseModel):
    message: str
    session_id: str = "default"


class GenerateBody(BaseModel):
    doc_type: str
    title: Optional[str] = None
    diagram_type: Optional[str] = None
    scenario: Optional[str] = None
    output_path: Optional[str] = None


class GenerateResponse(BaseModel):
    content: str
    filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/review")
async def review(body: ReviewBody) -> StreamingResponse:
    from pathlib import Path

    request = ReviewRequest(
        files=[Path(f) for f in body.files],
        auto_ticket=body.auto_ticket,
    )

    async def _stream() -> AsyncIterator[str]:
        async for chunk in _get_orchestrator().run_review(request):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/plain")


@app.post("/chat")
async def chat(body: ChatBody) -> StreamingResponse:
    async def _stream() -> AsyncIterator[str]:
        async for chunk in _get_orchestrator().run_chat(body.message, body.session_id):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/plain")


@app.post("/generate", response_model=GenerateResponse)
async def generate(body: GenerateBody) -> GenerateResponse:
    from pathlib import Path

    request = GenerateRequest(
        doc_type=body.doc_type,  # type: ignore[arg-type]
        title=body.title,
        diagram_type=body.diagram_type,
        scenario=body.scenario,
        output_path=Path(body.output_path) if body.output_path else None,
    )
    result = await _get_orchestrator().run_generate(request)
    return GenerateResponse(content=result.content, filename=result.filename)
